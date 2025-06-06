# Chatty
A chat app created using Cohere.

## Getting Started

### Prerequisites

- Python 3.8+
- (Recommended) Create and activate a virtual environment

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Chityalaakhil/Chatty.git
   cd Chatty
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   - Create a `.env` file in the root directory and add required environment variables (such as API keys for Cohere if needed).

### Running the Application

- **Development server (using Flask):**
  ```bash
  flask run
  ```
  or, if your app entry point is a file (e.g., `app.py`):
  ```bash
  python app.py
  ```

- **Production server (using Gunicorn):**
  ```bash
  gunicorn app:app
  ```

> Replace `app:app` with the appropriate module and application variable if different.

---

Feel free to update this with any specific configuration or startup scripts your project requires!
