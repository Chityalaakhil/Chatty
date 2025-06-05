// script.js
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatBox = document.getElementById("chat");
const toggleThemeBtn = document.getElementById("toggle-theme");
const clearHistoryBtn = document.getElementById("clear-history");

function addMessage(content, sender = "bot") {
  const div = document.createElement("div");
  div.className = `message ${sender}`;
  div.textContent = content;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}
        // const response = await fetch('http://127.0.0.1:5000/chat', {
async function sendMessage(message) {
  addMessage(message, "user");
  const res = await fetch("http://127.0.0.1:5000/chat-stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ message })
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let botMsg = document.createElement("div");
  botMsg.className = "message bot";
  chatBox.appendChild(botMsg);

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop();

    for (let part of parts) {
      if (part.startsWith("data: ")) {
        const json = JSON.parse(part.slice(6));
        botMsg.textContent = json.response;
        chatBox.scrollTop = chatBox.scrollHeight;
      }
    }
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  sendMessage(message);
  messageInput.value = "";
});
