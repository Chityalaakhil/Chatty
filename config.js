// config.js - Environment configuration
window.APP_CONFIG = {
  // Environment detection
  environment: (() => {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'development';
    } else if (hostname.includes('azurewebsites.net')) {
      return 'azure';
    } else {
      return 'production';
    }
  })(),

  // Base URLs for different environments
  baseUrls: {
    development: 'http://127.0.0.1:5000',
    azure: window.location.origin,
    production: window.location.origin
  },

  // Get the appropriate base URL
  getBaseUrl: function() {
    return this.baseUrls[this.environment];
  },

  // API configuration
  api: {
    timeout: 30000, // 30 seconds
    retries: 3
  },

  // Feature flags
  features: {
    enableDebugLogs: true,
    maxFileSize: 16 * 1024 * 1024, // 16MB
    allowedFileTypes: ['txt', 'pdf', 'docx', 'md']
  }
};

console.log('App Config Loaded:', window.APP_CONFIG);