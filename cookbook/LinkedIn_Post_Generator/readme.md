# LinkedIn Post Generator using eGet

Generate professional LinkedIn posts from any webpage using AI. This app uses eGet's content extraction capabilities along with AI to create engaging social media posts.

## Prerequisites

Before running the LinkedIn Post Generator, you need to have the following set up:

1. Python 3.9 or higher
2. Docker and Docker Compose for running eGet
3. (Optional) At least one of these:
   - Together.ai API key
   - Ollama installed locally
   - OpenAI API key

## Setup Steps

### 1. Start eGet Locally

First, we need to get eGet running:

```bash
# Clone eGet if you haven't already
git clone https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai.git
cd eGet-Crawler-for-ai

# Start eGet services
docker-compose up -d

# Verify eGet is running by visiting:
# http://localhost:8000/docs
```

### 2. Set Up LinkedIn Post Generator

Once eGet is running, set up the post generator:

```bash
# Navigate to the linkedin_post_maker directory
cd cookbook/linkedin_post_maker

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure AI Providers

You need at least one of these AI providers configured:

#### Option 1: Together.ai (Recommended)
1. Sign up at [Together.ai](https://www.together.ai)
2. Get your API key
3. Keep it ready to paste in the app

#### Option 2: Ollama (Local)
```bash
# Install Ollama from https://ollama.ai
# Then pull the required model:
ollama pull llama3.2

# Start Ollama service
ollama serve
```

#### Option 3: OpenAI
1. Get your API key from [OpenAI Platform](https://platform.openai.com)
2. Keep it ready to paste in the app

## Running the App

```bash
# Make sure you're in the linkedin_post_maker directory
# and your virtual environment is activated

streamlit run app.py
```

The app will be available at: http://localhost:8501

## Usage

1. Verify eGet is running at http://localhost:8000
2. Open the app at http://localhost:8501
3. Select your preferred AI provider in the sidebar
4. Enter API key if required
5. Paste any webpage URL
6. Click "Generate Post"
7. Copy and use the generated post on LinkedIn


