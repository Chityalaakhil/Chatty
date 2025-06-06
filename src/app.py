import cohere
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, render_template
import json
from flask_cors import CORS
from werkzeug.utils import secure_filename
import PyPDF2
import docx
import uuid
import logging
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
# import re

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()
# Make sure to add your COHERE_API_KEY to Azure App Service Configuration
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
if not COHERE_API_KEY:
    logger.error("COHERE_API_KEY environment variable is not set!")
    raise ValueError("COHERE_API_KEY environment variable is required")

co = cohere.ClientV2(api_key=COHERE_API_KEY)

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
MAX_CONTEXT_LENGTH = 100000  # Adjust based on model limits
CHUNK_SIZE = 500  # Size of text chunks for embedding
CHUNK_OVERLAP = 50  # Overlap between chunks
SIMILARITY_THRESHOLD = 0.3  # Minimum similarity score for relevance
MAX_RELEVANT_CHUNKS = 5  # Maximum number of chunks to include in context

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Simple memory store per user (can be replaced with a database)
memory = {}
# Store documents per user
user_documents = {}
# Store document embeddings per user
user_embeddings = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks for better embedding and retrieval"""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence or paragraph boundaries
        if end < len(text):
            # Look for sentence endings
            for i in range(min(50, chunk_size // 4)):  # Look back up to 50 chars
                if text[end - i] in '.!?\n':
                    end = end - i + 1
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
    logger.info(f"Split text into {len(chunks)} chunks")
    return chunks

def extract_text_from_file(file_path, filename):
    """Extract text content from various file types"""
    try:
        file_ext = filename.rsplit('.', 1)[1].lower()
        logger.info(f"Extracting text from {filename} (type: {file_ext})")
        
        if file_ext == 'txt' or file_ext == 'md':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
                logger.info(f"Extracted {len(content)} characters from {filename}")
                return content
        
        elif file_ext == 'pdf':
            text = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for i, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    text += page_text + "\n"
                    logger.debug(f"Extracted {len(page_text)} chars from page {i+1}")
            logger.info(f"Extracted {len(text)} characters from PDF {filename}")
            return text
        
        elif file_ext == 'docx':
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            logger.info(f"Extracted {len(text)} characters from DOCX {filename}")
            return text
        
        else:
            logger.error(f"Unsupported file type: {file_ext}")
            return None
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {str(e)}")
        return None

async def embed_texts(texts, input_type="search_document"):
    """Generate embeddings for texts using Cohere API"""
    try:
        logger.info(f"Generating embeddings for {len(texts)} texts")
        response = co.embed(
            texts=texts,
            model="embed-english-v3.0",
            input_type=input_type,
            embedding_types=["float"]
        )
        embeddings = response.embeddings.float_
        logger.info(f"Generated {len(embeddings)} embeddings")
        return embeddings
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        return None

def find_similar_chunks(query_embedding, document_chunks, top_k=MAX_RELEVANT_CHUNKS):
    """Find most similar document chunks to query using cosine similarity"""
    if not document_chunks:
        return []
    
    # Collect all embeddings and metadata
    all_embeddings = []
    chunk_metadata = []
    
    for doc_id, doc_info in document_chunks.items():
        for i, chunk_data in enumerate(doc_info['chunks']):
            all_embeddings.append(chunk_data['embedding'])
            chunk_metadata.append({
                'doc_id': doc_id,
                'chunk_index': i,
                'text': chunk_data['text'],
                'filename': doc_info['filename']
            })
    
    if not all_embeddings:
        return []
    
    # Calculate similarities
    similarities = cosine_similarity([query_embedding], all_embeddings)[0]
    
    # Get top-k most similar chunks above threshold
    similar_indices = np.argsort(similarities)[::-1]
    
    relevant_chunks = []
    for idx in similar_indices[:top_k]:
        if similarities[idx] >= SIMILARITY_THRESHOLD:
            chunk_info = chunk_metadata[idx].copy()
            chunk_info['similarity'] = float(similarities[idx])
            relevant_chunks.append(chunk_info)
    
    logger.info(f"Found {len(relevant_chunks)} relevant chunks above threshold {SIMILARITY_THRESHOLD}")
    return relevant_chunks

def get_memory(user_id):
    return memory.get(user_id, [])

def update_memory(user_id, user_msg, bot_msg):
    memory.setdefault(user_id, []).append({"role": "user", "content": user_msg})
    memory[user_id].append({"role": "chatbot", "content": bot_msg})
    # Limit memory to last 10 messages
    memory[user_id] = memory[user_id][-10:]
    logger.debug(f"Updated memory for user {user_id}: {len(memory[user_id])} messages")

def get_user_documents(user_id):
    docs = user_documents.get(user_id, [])
    logger.debug(f"Retrieved {len(docs)} documents for user {user_id}")
    return docs

def get_user_embeddings(user_id):
    embeddings = user_embeddings.get(user_id, {})
    logger.debug(f"Retrieved embeddings for {len(embeddings)} documents for user {user_id}")
    return embeddings

def add_user_document(user_id, doc_info):
    user_documents.setdefault(user_id, []).append(doc_info)
    logger.info(f"Added document {doc_info['filename']} for user {user_id}")

def store_document_embeddings(user_id, doc_id, filename, chunks_with_embeddings):
    user_embeddings.setdefault(user_id, {})[doc_id] = {
        'filename': filename,
        'chunks': chunks_with_embeddings
    }
    logger.info(f"Stored embeddings for document {filename} (user {user_id})")

def prepare_semantic_context(query, user_id, max_length=MAX_CONTEXT_LENGTH):
    """Prepare document context using semantic similarity search"""
    try:
        # Generate embedding for the query
        query_embeddings = co.embed(
            texts=[query],
            model="embed-english-v3.0",
            input_type="search_query",
            embedding_types=["float"]
        )
        query_embedding = query_embeddings.embeddings.float_[0]
        
        # Get user's document embeddings
        document_chunks = get_user_embeddings(user_id)
        
        if not document_chunks:
            logger.info("No document embeddings found for semantic search")
            return ""
        
        # Find similar chunks
        relevant_chunks = find_similar_chunks(query_embedding, document_chunks)
        
        if not relevant_chunks:
            logger.info("No relevant chunks found above similarity threshold")
            return ""
        
        # Build context from relevant chunks
        context_parts = []
        current_length = 0
        
        for chunk_info in relevant_chunks:
            doc_header = f"\n=== Document: {chunk_info['filename']} (Similarity: {chunk_info['similarity']:.3f}) ===\n"
            chunk_content = chunk_info['text']
            
            # Check length limits
            section_length = len(doc_header) + len(chunk_content)
            if current_length + section_length > max_length:
                break
            
            context_parts.append(doc_header + chunk_content)
            current_length += section_length
        
        context = "\n".join(context_parts)
        logger.info(f"Prepared semantic context: {len(context)} characters from {len(context_parts)} relevant chunks")
        return context
        
    except Exception as e:
        logger.error(f"Error in semantic search: {str(e)}")
        return ""

def prepare_document_context(docs, max_length=MAX_CONTEXT_LENGTH):
    """Prepare document context with length limits (fallback method)"""
    if not docs:
        return ""
    
    context_parts = []
    current_length = 0
    
    for doc in docs:
        doc_header = f"\n=== Document: {doc['filename']} ===\n"
        doc_content = doc['content']
        
        # Truncate if too long
        available_space = max_length - current_length - len(doc_header)
        if available_space <= 0:
            break
            
        if len(doc_content) > available_space:
            doc_content = doc_content[:available_space] + "\n[Content truncated...]"
        
        context_parts.append(doc_header + doc_content)
        current_length += len(doc_header) + len(doc_content)
        
        if current_length >= max_length:
            break
    
    context = "\n".join(context_parts)
    logger.info(f"Prepared document context: {len(context)} characters from {len(context_parts)} documents")
    return context

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "upload_folder": app.config['UPLOAD_FOLDER']
    })

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_document():
    logger.info("Document upload request received")
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    user_id = request.form.get('user_id', 'default')
    
    logger.info(f"Upload request from user {user_id}, file: {file.filename}")
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Supported types: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
    
    try:
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save file
        file.save(file_path)
        logger.info(f"File saved to {file_path}")
        
        # Extract text content
        text_content = extract_text_from_file(file_path, filename)
        
        if text_content is None:
            os.remove(file_path)  # Clean up
            return jsonify({"error": "Failed to extract text from file"}), 400
        
        if not text_content.strip():
            os.remove(file_path)  # Clean up
            return jsonify({"error": "No text content found in file"}), 400
        
        # Split text into chunks
        text_chunks = chunk_text(text_content)
        
        # Generate embeddings for chunks
        try:
            embeddings = co.embed(
                texts=text_chunks,
                model="embed-english-v3.0",
                input_type="search_document",
                embedding_types=["float"]
            )
            chunk_embeddings = embeddings.embeddings.float_
            
            # Prepare chunks with embeddings
            chunks_with_embeddings = []
            for i, (chunk, embedding) in enumerate(zip(text_chunks, chunk_embeddings)):
                chunks_with_embeddings.append({
                    'text': chunk,
                    'embedding': embedding,
                    'chunk_index': i
                })
            
            logger.info(f"Generated embeddings for {len(chunks_with_embeddings)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)}")
            os.remove(file_path)  # Clean up
            return jsonify({"error": f"Failed to generate embeddings: {str(e)}"}), 500
        
        # Store document info
        doc_id = str(uuid.uuid4())
        doc_info = {
            "id": doc_id,
            "filename": filename,
            "file_path": file_path,
            "content": text_content,
            "upload_time": str(os.path.getctime(file_path)),
            "content_length": len(text_content),
            "chunk_count": len(text_chunks)
        }
        
        add_user_document(user_id, doc_info)
        store_document_embeddings(user_id, doc_id, filename, chunks_with_embeddings)
        
        return jsonify({
            "message": "Document uploaded and processed successfully",
            "document_id": doc_id,
            "filename": filename,
            "content_length": len(text_content),
            "chunk_count": len(text_chunks),
            "content_preview": text_content[:200] + "..." if len(text_content) > 200 else text_content
        })
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@app.route("/documents", methods=["GET"])
def list_documents():
    user_id = request.args.get('user_id', 'default')
    docs = get_user_documents(user_id)
    
    # Return summary of documents (without full content)
    doc_summaries = []
    for doc in docs:
        doc_summaries.append({
            "id": doc["id"],
            "filename": doc["filename"],
            "upload_time": doc["upload_time"],
            "content_length": doc.get("content_length", len(doc["content"])),
            "chunk_count": doc.get("chunk_count", 0),
            "content_preview": doc["content"][:100] + "..." if len(doc["content"]) > 100 else doc["content"]
        })
    
    logger.info(f"Listed {len(doc_summaries)} documents for user {user_id}")
    return jsonify({"documents": doc_summaries})

@app.route("/search", methods=["POST"])
def semantic_search():
    """Endpoint for testing semantic search functionality"""
    data = request.get_json()
    user_id = data.get("user_id", "default")
    query = data.get("query", "").strip()
    
    if not query:
        return jsonify({"error": "Query is required"}), 400
    
    try:
        context = prepare_semantic_context(query, user_id)
        
        return jsonify({
            "query": query,
            "context_length": len(context),
            "context": context[:1000] + "..." if len(context) > 1000 else context,
            "has_results": len(context) > 0
        })
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    message = data.get("message", "").strip()
    use_documents = data.get("use_documents", False)

    logger.info(f"Chat request from user {user_id}, use_documents: {use_documents}")
    logger.debug(f"Message: {message[:100]}...")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    messages = get_memory(user_id) + [{"role": "user", "content": message}]
    
    # If using documents, add document context with semantic search
    if use_documents:
        logger.info("Using semantic search for document context")
        doc_context = prepare_semantic_context(message, user_id)
        
        if doc_context:
            system_message = {
                "role": "system", 
                "content": f"""You are a helpful assistant with access to the user's documents. Use the following relevant document excerpts to answer questions:

{doc_context}

Instructions:
- The document excerpts above were selected based on semantic similarity to the user's question
- Each excerpt shows the document name and similarity score
- Use this information to provide accurate, specific answers
- Always cite which document you're referencing
- If the excerpts don't contain relevant information, say so clearly
"""
            }
            messages = [system_message] + messages
            logger.info(f"Added semantic document context ({len(doc_context)} chars)")
        else:
            # Fallback to regular document context if semantic search fails
            docs = get_user_documents(user_id)
            if docs:
                doc_context = prepare_document_context(docs)
                if doc_context:
                    system_message = {
                        "role": "system", 
                        "content": f"""You are a helpful assistant with access to the user's documents:

{doc_context}

Instructions:
- Use the document information above to answer questions when relevant
- Always specify which document you're referencing
- If the question cannot be answered from the documents, say so clearly
"""
                    }
                    messages = [system_message] + messages
                    logger.info("Used fallback document context")

    try:
        logger.debug(f"Sending {len(messages)} messages to Cohere")
        response = co.chat(model="command-r-plus-08-2024", messages=messages)
        bot_response = response.message.content[0].text
        
        update_memory(user_id, message, bot_response)
        logger.info(f"Chat response generated ({len(bot_response)} chars)")
        
        return jsonify({"response": bot_response})
    
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return jsonify({"error": f"Chat failed: {str(e)}"}), 500

@app.route("/chat-stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    message = data.get("message", "").strip()
    use_documents = data.get("use_documents", False)

    logger.info(f"Stream chat request from user {user_id}, use_documents: {use_documents}")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    messages = get_memory(user_id) + [{"role": "user", "content": message}]
    
    # If using documents, add document context with semantic search
    if use_documents:
        logger.info("Using semantic search for streaming chat")
        doc_context = prepare_semantic_context(message, user_id)
        
        if doc_context:
            system_message = {
                "role": "system", 
                "content": f"""You are a helpful assistant with access to the user's documents. Use the following relevant document excerpts to answer questions:

{doc_context}

Instructions:
- The document excerpts above were selected based on semantic similarity to the user's question
- Each excerpt shows the document name and similarity score
- Use this information to provide accurate, specific answers
- Always cite which document you're referencing
- If the excerpts don't contain relevant information, say so clearly
"""
            }
            messages = [system_message] + messages
            logger.info(f"Added semantic document context to streaming chat")
        else:
            # Fallback to regular document context
            docs = get_user_documents(user_id)
            if docs:
                doc_context = prepare_document_context(docs)
                if doc_context:
                    system_message = {
                        "role": "system", 
                        "content": f"""You are a helpful assistant with access to the user's documents:

{doc_context}

Instructions:
- Use the document information above to answer questions when relevant
- Always specify which document you're referencing
- If the question cannot be answered from the documents, say so clearly
"""
                    }
                    messages = [system_message] + messages
                    logger.info("Used fallback document context for streaming")

    def stream():
        try:
            response = co.chat_stream(model="command-r-plus-08-2024", messages=messages)
            response_text = ""
            for chunk in response:
                if chunk and chunk.type == "content-delta":
                    delta_text = chunk.delta.message.content.text
                    response_text += delta_text
                    yield f"data: {json.dumps({'response': response_text})}\n\n"
            
            update_memory(user_id, message, response_text)
            yield "data: [DONE]\n\n"
            logger.info(f"Streaming chat completed ({len(response_text)} chars)")
            
        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream(), mimetype="text/event-stream")

@app.route("/delete-document", methods=["DELETE"])
def delete_document():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    document_id = data.get("document_id")
    
    logger.info(f"Delete document request from user {user_id}, doc_id: {document_id}")
    
    if not document_id:
        return jsonify({"error": "Document ID is required"}), 400
    
    docs = get_user_documents(user_id)
    doc_to_remove = None
    
    for i, doc in enumerate(docs):
        if doc["id"] == document_id:
            doc_to_remove = i
            break
    
    if doc_to_remove is not None:
        doc = docs.pop(doc_to_remove)
        
        # Remove embeddings
        embeddings = user_embeddings.get(user_id, {})
        if document_id in embeddings:
            del embeddings[document_id]
            logger.info(f"Removed embeddings for document {document_id}")
        
        # Clean up file
        try:
            if os.path.exists(doc["file_path"]):
                os.remove(doc["file_path"])
                logger.info(f"Deleted file: {doc['file_path']}")
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
        
        return jsonify({"message": "Document deleted successfully"})
    else:
        return jsonify({"error": "Document not found"}), 404

# Debug endpoint to check document status
@app.route("/debug/user-state", methods=["GET"])
def debug_user_state():
    user_id = request.args.get('user_id', 'default')
    docs = get_user_documents(user_id)
    memory_msgs = get_memory(user_id)
    embeddings = get_user_embeddings(user_id)
    
    return jsonify({
        "user_id": user_id,
        "documents_count": len(docs),
        "documents": [{"id": doc["id"], "filename": doc["filename"], "content_length": len(doc["content"]), "chunk_count": doc.get("chunk_count", 0)} for doc in docs],
        "embeddings_count": len(embeddings),
        "memory_count": len(memory_msgs),
        "memory": memory_msgs[-3:] if memory_msgs else []  # Last 3 messages
    })

if __name__ == "__main__":
    # For local development
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # For Azure deployment
    # Azure will handle the WSGI server
    pass