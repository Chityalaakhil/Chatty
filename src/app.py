import cohere
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, render_template
import json
from flask_cors import CORS

load_dotenv()
co = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))


app = Flask(__name__)
CORS(app)

# Simple memory store per user (can be replaced with a database)
memory = {}

def get_memory(user_id):
    return memory.get(user_id, [])

def update_memory(user_id, user_msg, bot_msg):
    memory.setdefault(user_id, []).append({"role": "user", "content": user_msg})
    memory[user_id].append({"role": "chatbot", "content": bot_msg})
    # Limit memory to last 10 messages
    # will have to adjust this later as needed
    memory[user_id] = memory[user_id][-10:]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Message is required"}), 400

    messages = get_memory(user_id) + [{"role": "user", "content": message}]
    response = co.chat(model="command-a-03-2025", messages=messages)

    bot_response = response.message.content[0].text
    update_memory(user_id, message, bot_response)

    return jsonify({"response": bot_response})

@app.route("/chat-stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Message is required"}), 400

    messages = get_memory(user_id) + [{"role": "user", "content": message}]
    print(f"Streaming chat for user {user_id}: {messages}")

    def stream():
        try:
            response = co.chat_stream(model="command-a-03-2025", messages=messages)
            response_text = ""
            for chunk in response:
                if chunk and chunk.type == "content-delta":
                    delta_text = chunk.delta.message.content.text
                    response_text += delta_text
                    yield f"data: {json.dumps({'response': response_text})}\n\n"
            update_memory(user_id, message, response_text)
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=False)
