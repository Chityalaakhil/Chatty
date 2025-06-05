import cohere
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import json
from flask_cors import CORS

load_dotenv()
co = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))


app = Flask(__name__)
CORS(app)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data["message"]
    if not message or message.strip() == "":
        return jsonify({"error": "Message is required"}), 400
    response = co.chat(
        model="command-a-03-2025",
        messages = [
            {
                "role": "user", 
                "content": message
            }
        ]
    )
    print(response)
    return jsonify({"response": response.message.content[0].text})

@app.route("/chat-stream", methods=["POST"])
def chat_stream():
    data = request.json
    message = data["message"]
    if not message or message.strip() == "":
        return jsonify({"error": "Message is required"}), 400
    
    def generate_response():
        response = co.chat_stream(
            model="command-a-03-2025",
            messages = [
                {
                    "role": "user", 
                    "content": message
                }
            ]
        )
        response_text = ""
        for chunk in response:
            if chunk and chunk.type == "content-delta":
                response_text += chunk.delta.message.content.text
                yield f"data: {json.dumps({'response': response_text})}\n\n"
        yield "data: [DONE]\n\n"
        

    return app.response_class(generate_response(), mimetype='application/json')

if __name__ == "__main__":
    app.run(debug=True)
