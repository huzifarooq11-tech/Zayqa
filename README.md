
# Zayqa – AI-Powered Voice Ordering & Restaurant POS

Zayqa is an AI-powered restaurant order management system that allows restaurant staff to manage dine-in orders using natural voice commands.

Instead of manually entering orders, staff can speak naturally, and the AI system interprets their instructions, processes the order, and updates the dashboard in real time.

## Features

- Voice-based restaurant order management
- English and Urdu voice interaction support
- Real-time speech recognition
- AI-powered order interpretation
- Add, update and manage menu items in orders
- Table-based order management
- Real-time dashboard updates
- Voice confirmations
- Order data storage using SQLite

## Technology Stack

- Python
- FastAPI
- Gladia Solaria-1 – Speech-to-Text
- Groq API – GPT-OSS-120B
- Edge TTS – Text-to-Speech
- SQLite
- HTML
- CSS
- JavaScript
- WebSockets
- AudioWorklet

## Workflow

1. The restaurant staff speaks an order.
2. The browser captures the microphone audio.
3. Audio is streamed through WebSockets.
4. Gladia converts speech into text.
5. Groq GPT-OSS-120B interprets the order.
6. The Python backend validates and processes the instructions.
7. The order is saved in SQLite.
8. The dashboard updates in real time.
9. Edge TTS generates a spoken confirmation.

## Installation

Clone the repository:

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
```

Move into the project folder:

```bash
cd KarachiRelay
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file and add your API credentials:

```env
GLADIA_API_KEY=your_gladia_api_key
GROQ_API_KEY=your_groq_api_key
```

Do not share your actual API keys.

## Run the Application

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the application in your browser:

http://127.0.0.1:8000

## Project Type

AI Agent + Voice Assistant

Zayqa uses an AI model to interpret natural-language order commands and a Python backend to validate and execute order operations.

## Developer

Software Engineering Student | AI & Python Enthusiast
