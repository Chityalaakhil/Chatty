// Enhanced script.js with semantic search capabilities
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
const uploadProgress = document.getElementById("uploadProgress");
const documentsList = document.getElementById("documentsList");
const useDocumentsCheckbox = document.getElementById("useDocuments");

// Search-related elements
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const searchResults = document.getElementById("searchResults");

// Status elements
const statusIndicator = document.getElementById("statusIndicator");
const statusText = document.getElementById("statusText");

// Configuration for different environments
const CONFIG = {
  getBaseUrl: function() {
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return 'http://127.0.0.1:5000';
    }
    return window.location.origin;
  },

  endpoints: {
    chat: '/chat-stream',
    upload: '/upload',
    documents: '/documents',
    deleteDocument: '/delete-document',
    search: '/search',
    debug: '/debug/user-state'
  }
};

// Generate unique user ID
const userId = 'user_' + Math.random().toString(36).substr(2, 9);

// State
let useDocuments = false;
let isUploading = false;

// Utility function to build full URL
function buildUrl(endpoint) {
  const baseUrl = CONFIG.getBaseUrl();
  return `${baseUrl}${endpoint}`;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  console.log('Cohere Chat initialized');
  console.log('Base URL:', CONFIG.getBaseUrl());
  console.log('User ID:', userId);
  loadDocuments();
  setupEventListeners();
});

function setupEventListeners() {
  // Chat functionality
  chatForm.addEventListener("submit", handleChatSubmit);
  clearHistoryBtn.addEventListener("click", clearHistory);

  // Document functionality
  uploadArea.addEventListener('click', () => !isUploading && fileInput.click());
  uploadArea.addEventListener('dragover', handleDragOver);
  uploadArea.addEventListener('dragleave', handleDragLeave);
  uploadArea.addEventListener('drop', handleDrop);
  fileInput.addEventListener('change', handleFileSelect);
  useDocumentsCheckbox.addEventListener('change', handleDocumentToggle);

  // Search functionality
  searchBtn.addEventListener('click', handleSearch);
  searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSearch();
    }
  });

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
              botMsg.innerHTML = formatMessage(json.response);
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

function formatMessage(text) {
  // Basic formatting for better readability
  return text
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
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

function updateStatus() {
  if (useDocuments) {
    statusIndicator.classList.add('documents-active');
    statusText.textContent = 'Document Mode';
  } else {
    statusIndicator.classList.remove('documents-active');
    statusText.textContent = 'General Mode';
  }
}

function handleDocumentToggle(e) {
  useDocuments = e.target.checked;
  updateStatus();

  const statusMessage = useDocuments 
    ? "📚 Document mode enabled - I'll use semantic search to find relevant information from your documents" 
    : "💬 Document mode disabled - I'll answer from general knowledge";
  addMessage(statusMessage, "system");
}

function handleDragOver(e) {
  e.preventDefault();
  if (!isUploading) {
    uploadArea.classList.add('dragover');
  }
}

function handleDragLeave(e) {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  if (!isUploading) {
    const files = e.dataTransfer.files;
    handleFiles(files);
  }
}

function handleFileSelect(e) {
  if (!isUploading) {
    handleFiles(e.target.files);
  }
}

function showUploadProgress(show = true) {
  isUploading = show;
  uploadProgress.style.display = show ? 'block' : 'none';
  uploadArea.classList.toggle('uploading', show);

  if (show) {
    uploadArea.querySelector('.upload-text').textContent = 'Processing files...';
    uploadArea.querySelector('.upload-hint').textContent = 'Please wait while we extract and embed content';
  } else {
    uploadArea.querySelector('.upload-text').textContent = 'Click or drag files here';
    uploadArea.querySelector('.upload-hint').textContent = 'Supports: PDF, DOCX, TXT, MD';
  }
}

async function handleFiles(files) {
  if (files.length === 0) return;

  showUploadProgress(true);
  let successCount = 0;
  let totalFiles = files.length;

  for (const file of files) {
    try {
      await uploadFile(file);
      successCount++;
    } catch (error) {
      console.error(`Failed to upload ${file.name}:`, error);
    }
  }

  showUploadProgress(false);
  loadDocuments();

  // Show summary message
  if (successCount > 0) {
    const message = totalFiles === 1 
      ? `✅ Document uploaded and processed with semantic embeddings!`
      : `✅ ${successCount}/${totalFiles} documents uploaded and processed with semantic embeddings!`;
    addMessage(message, "system");
  }
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('user_id', userId);

  const url = buildUrl(CONFIG.endpoints.upload);
  const response = await fetch(url, {
    method: 'POST',
    body: formData
  });

  const result = await response.json();

  if (!response.ok) {
    throw new Error(result.error || 'Upload failed');
  }

  console.log('Upload successful:', result);
  return result;
}

async function loadDocuments() {
  try {
    const url = buildUrl(`${CONFIG.endpoints.documents}?user_id=${userId}`);
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
              <span>📄 ${doc.content_length || 'Unknown'} chars</span>
              <span>🧩 ${doc.chunk_count || 0} chunks</span>
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
      addMessage(result.message, 'system');
      loadDocuments();
    } else {
      addMessage(`Error: ${result.error}`, 'system');
    }
  } catch (error) {
    console.error('Delete error:', error);
    addMessage(`Error deleting document: ${error.message}`, 'system');
  }
}

// Search functionality
async function handleSearch() {
  const query = searchInput.value.trim();
  if (!query) return;

  searchBtn.disabled = true;
  searchBtn.textContent = 'Searching...';

  try {
    const url = buildUrl(CONFIG.endpoints.search);
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: userId,
        query: query,
        limit: 5
      })
    });

    const result = await response.json();

    if (response.ok) {
      displaySearchResults(result.results);
      addMessage(`🔍 Found ${result.results.length} relevant document sections for: "${query}"`, 'system');
    } else {
      addMessage(`Search error: ${result.error}`, 'system');
    }
  } catch (error) {
    console.error('Search error:', error);
    addMessage(`Search error: ${error.message}`, 'system');
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = 'Search';
  }
}

function displaySearchResults(results) {
  searchResults.innerHTML = '';

  if (results.length === 0) {
    searchResults.innerHTML = '<div class="search-result-item">No results found</div>';
  } else {
    results.forEach(result => {
      const resultElement = document.createElement('div');
      resultElement.className = 'search-result-item';
      resultElement.innerHTML = `
        <div class="search-result-header">
          ${escapeHtml(result.filename)}
          <span class="similarity-score">${Math.round(result.similarity * 100)}%</span>
        </div>
        <div class="search-result-snippet">${escapeHtml(result.content)}</div>
      `;
      searchResults.appendChild(resultElement);
    });
  }

  searchResults.style.display = 'block';
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
  if (!text) return '';
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