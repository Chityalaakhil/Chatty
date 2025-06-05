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
# Update the upload folder path for Azure
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
MAX_CONTEXT_LENGTH = 100000  # Adjust based on model limits

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Simple memory store per user (can be replaced with a database)
memory = {}
# Store documents per user
user_documents = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

def get_memory(user_id):
    return memory.get(user_id, [])

def update_memory(user_id, user_msg, bot_msg):
    memory.setdefault(user_id, []).append({"role": "user", "content": user_msg})
    memory[user_id].append({"role": "chatbot", "content": bot_msg})
    # Limit memory to last 10 messages
    # will have to adjust this later as needed
    memory[user_id] = memory[user_id][-10:]
    logger.debug(f"Updated memory for user {user_id}: {len(memory[user_id])} messages")

def get_user_documents(user_id):
    docs = user_documents.get(user_id, [])
    logger.debug(f"Retrieved {len(docs)} documents for user {user_id}")
    return docs

def add_user_document(user_id, doc_info):
    user_documents.setdefault(user_id, []).append(doc_info)
    logger.info(f"Added document {doc_info['filename']} for user {user_id}")

def prepare_document_context(docs, max_length=MAX_CONTEXT_LENGTH):
    """Prepare document context with length limits"""
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
        
        # Store document info
        doc_info = {
            "id": str(uuid.uuid4()),
            "filename": filename,
            "file_path": file_path,
            "content": text_content,
            "upload_time": str(os.path.getctime(file_path)),
            "content_length": len(text_content)
        }
        
        add_user_document(user_id, doc_info)
        
        return jsonify({
            "message": "Document uploaded successfully",
            "document_id": doc_info["id"],
            "filename": filename,
            "content_length": len(text_content),
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
            "content_preview": doc["content"][:100] + "..." if len(doc["content"]) > 100 else doc["content"]
        })
    
    logger.info(f"Listed {len(doc_summaries)} documents for user {user_id}")
    return jsonify({"documents": doc_summaries})

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
    
    # If using documents, add document context
    if use_documents:
        docs = get_user_documents(user_id)
        logger.info(f"Found {len(docs)} documents for context")
        
        if docs:
            # Prepare document context
            doc_context = prepare_document_context(docs)
            
            if doc_context:
                # Add system message with document context
                system_message = {
                    "role": "system", 
                    "content": f"""You are a helpful assistant with access to the user's documents. Use the following documents to answer questions when relevant:

{doc_context}

Instructions:
- If the user's question can be answered using information from these documents, please reference the specific document name and provide accurate information.
- If the question cannot be answered from the documents, please say so clearly and provide a general response if possible.
- Always be specific about which document you're referencing when using document information.
"""
                }
                messages = [system_message] + messages
                logger.info(f"Added document context ({len(doc_context)} chars) to messages")
            else:
                logger.warning("No document context prepared despite having documents")
        else:
            logger.info("No documents found for user, proceeding without document context")

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
    
    # If using documents, add document context
    if use_documents:
        docs = get_user_documents(user_id)
        if docs:
            doc_context = prepare_document_context(docs)
            
            if doc_context:
                system_message = {
                    "role": "system", 
                    "content": f"""You are a helpful assistant with access to the user's documents. Use the following documents to answer questions when relevant:

{doc_context}

Instructions:
- If the user's question can be answered using information from these documents, please reference the specific document name and provide accurate information.
- If the question cannot be answered from the documents, please say so clearly and provide a general response if possible.
- Always be specific about which document you're referencing when using document information.
"""
                }
                messages = [system_message] + messages
                logger.info(f"Added document context to streaming chat")

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
    
    return jsonify({
        "user_id": user_id,
        "documents_count": len(docs),
        "documents": [{"id": doc["id"], "filename": doc["filename"], "content_length": len(doc["content"])} for doc in docs],
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