// script.js - Azure-ready version with dynamic URL handling
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatBox = document.getElementById("chat");
const clearHistoryBtn = document.getElementById("clear-history");

// Document-related elements
const documentSidebar = document.getElementById("documentSidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const menuBtn = document.getElementById("menuBtn");
const fileInput = document.getElementById("fileInput");
const uploadArea = document.getElementById("uploadArea");
const documentsList = document.getElementById("documentsList");
const useDocumentsCheckbox = document.getElementById("useDocuments");

// Configuration for different environments
const CONFIG = {
  // Base URL configuration
  getBaseUrl: function() {
    // For local development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return 'http://127.0.0.1:5000';
    }
    // For Azure or other production environments
    // Use the same origin as the current page
    return window.location.origin;
  },
  
  // API endpoints
  endpoints: {
    chat: '/chat-stream',
    upload: '/upload',
    documents: '/documents',
    deleteDocument: '/delete-document',
    debug: '/debug/user-state'
  }
};

// Generate unique user ID
const userId = 'user_' + Math.random().toString(36).substr(2, 9);

// State
let useDocuments = false;

// Utility function to build full URL
function buildUrl(endpoint) {
  const baseUrl = CONFIG.getBaseUrl();
  return `${baseUrl}${endpoint}`;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  console.log('Base URL:', CONFIG.getBaseUrl());
  console.log('User ID:', userId);
  loadDocuments();
  setupEventListeners();
});

function setupEventListeners() {
  // Existing chat functionality
  chatForm.addEventListener("submit", handleChatSubmit);
  clearHistoryBtn.addEventListener("click", clearHistory);
  
  // Document functionality
  uploadArea.addEventListener('click', () => fileInput.click());
  uploadArea.addEventListener('dragover', handleDragOver);
  uploadArea.addEventListener('dragleave', handleDragLeave);
  uploadArea.addEventListener('drop', handleDrop);
  fileInput.addEventListener('change', handleFileSelect);
  useDocumentsCheckbox.addEventListener('change', handleDocumentToggle);
  
  // Mobile menu
  menuBtn.addEventListener('click', toggleSidebar);
  sidebarToggle.addEventListener('click', toggleSidebar);
  
  // Close sidebar when clicking outside on mobile
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && 
        !documentSidebar.contains(e.target) && 
        !menuBtn.contains(e.target) &&
        documentSidebar.classList.contains('open')) {
      documentSidebar.classList.remove('open');
    }
  });
}

function addMessage(content, sender = "bot") {
  const div = document.createElement("div");
  div.className = `message ${sender}`;
  div.textContent = content;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
  return div;
}

function showTypingIndicator() {
  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  indicator.textContent = "Typing...";
  indicator.style.display = "block";
  chatBox.appendChild(indicator);
  chatBox.scrollTop = chatBox.scrollHeight;
  return indicator;
}

async function sendMessage(message) {
  addMessage(message, "user");
  
  const typingIndicator = showTypingIndicator();
  const sendButton = chatForm.querySelector('button[type="submit"]');
  sendButton.disabled = true;
  
  try {
    const url = buildUrl(CONFIG.endpoints.chat);
    console.log('Sending message to:', url);
    
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ 
        message,
        user_id: userId,
        use_documents: useDocuments
      })
    });

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    
    // Remove typing indicator and create bot message
    typingIndicator.remove();
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
          const dataStr = part.slice(6);
          if (dataStr === "[DONE]") {
            break;
          }
          
          try {
            const json = JSON.parse(dataStr);
            if (json.response) {
              botMsg.textContent = json.response;
              chatBox.scrollTop = chatBox.scrollHeight;
            } else if (json.error) {
              botMsg.textContent = `Error: ${json.error}`;
              botMsg.style.color = "#dc3545";
            }
          } catch (e) {
            console.error("Error parsing JSON:", e);
          }
        }
      }
    }
  } catch (error) {
    console.error('Chat error:', error);
    typingIndicator.remove();
    addMessage(`Error: ${error.message}`, "bot");
  } finally {
    sendButton.disabled = false;
  }
}

function handleChatSubmit(e) {
  e.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  sendMessage(message);
  messageInput.value = "";
}

function clearHistory() {
  const messages = chatBox.querySelectorAll('.message');
  messages.forEach(msg => msg.remove());
  addMessage("Chat history cleared. How can I help you?", "bot");
}

// Document functionality
function toggleSidebar() {
  documentSidebar.classList.toggle('open');
}

function handleDocumentToggle(e) {
  useDocuments = e.target.checked;
  console.log('Document mode:', useDocuments ? 'ON' : 'OFF');
  
  // Show user feedback about document mode
  const statusMessage = useDocuments 
    ? "Document mode enabled - I'll use your uploaded documents to answer questions" 
    : "Document mode disabled - I'll answer from general knowledge";
  addMessage(statusMessage, "bot");
}

function handleDragOver(e) {
  e.preventDefault();
  uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  const files = e.dataTransfer.files;
  handleFiles(files);
}

function handleFileSelect(e) {
  handleFiles(e.target.files);
}

async function handleFiles(files) {
  for (const file of files) {
    await uploadFile(file);
  }
  loadDocuments();
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('user_id', userId);

  try {
    const url = buildUrl(CONFIG.endpoints.upload);
    console.log('Uploading file to:', url);
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData
    });
    
    const result = await response.json();
    
    if (response.ok) {
      addMessage(`Document "${file.name}" uploaded successfully! Content length: ${result.content_length} characters`, 'bot');
      console.log('Upload successful:', result);
    } else {
      addMessage(`Failed to upload "${file.name}": ${result.error}`, 'bot');
      console.error('Upload failed:', result);
    }
  } catch (error) {
    console.error('Upload error:', error);
    addMessage(`Error uploading "${file.name}": ${error.message}`, 'bot');
  }
}

async function loadDocuments() {
  try {
    const url = buildUrl(`${CONFIG.endpoints.documents}?user_id=${userId}`);
    console.log('Loading documents from:', url);
    
    const response = await fetch(url);
    const result = await response.json();
    
    documentsList.innerHTML = '';
    
    if (result.documents && result.documents.length > 0) {
      result.documents.forEach(doc => {
        const docElement = document.createElement('div');
        docElement.className = 'document-item';
        docElement.innerHTML = `
          <div class="document-info">
            <div class="document-name">${escapeHtml(doc.filename)}</div>
            <div class="document-meta">
              <small>Size: ${doc.content_length || 'Unknown'} chars</small>
            </div>
            <div class="document-preview">${escapeHtml(doc.content_preview)}</div>
          </div>
          <button class="delete-btn" onclick="deleteDocument('${doc.id}')" title="Delete document">×</button>
        `;
        documentsList.appendChild(docElement);
      });
      
      console.log(`Loaded ${result.documents.length} documents`);
    } else {
      documentsList.innerHTML = '<div class="no-documents">No documents uploaded yet</div>';
    }
  } catch (error) {
    console.error('Error loading documents:', error);
    documentsList.innerHTML = '<div class="no-documents">Error loading documents</div>';
  }
}

async function deleteDocument(documentId) {
  try {
    const url = buildUrl(CONFIG.endpoints.deleteDocument);
    console.log('Deleting document:', documentId);
    
    const response = await fetch(url, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: userId,
        document_id: documentId
      })
    });
    
    const result = await response.json();
    
    if (response.ok) {
      addMessage(result.message, 'bot');
      loadDocuments();
    } else {
      addMessage(`Error: ${result.error}`, 'bot');
    }
  } catch (error) {
    console.error('Delete error:', error);
    addMessage(`Error deleting document: ${error.message}`, 'bot');
  }
}

// Debug function to check user state (useful for troubleshooting)
async function debugUserState() {
  try {
    const url = buildUrl(`${CONFIG.endpoints.debug}?user_id=${userId}`);
    const response = await fetch(url);
    const result = await response.json();
    console.log('User state:', result);
    return result;
  } catch (error) {
    console.error('Debug error:', error);
  }
}

// Utility function to escape HTML
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Make functions available globally for onclick handlers and debugging
window.deleteDocument = deleteDocument;
window.debugUserState = debugUserState;

// Add environment info to console for debugging
console.log('Environment Info:', {
  hostname: window.location.hostname,
  origin: window.location.origin,
  baseUrl: CONFIG.getBaseUrl(),
  isLocal: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
});