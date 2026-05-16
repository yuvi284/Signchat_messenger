# Indian Sign Language (ISL) Translator & Chat Platform

![ISL App Banner](https://via.placeholder.com/1000x300?text=Indian+Sign+Language+Chat+%26+Translator)

A comprehensive, real-time communication platform designed to bridge the communication gap between individuals who use Indian Sign Language (ISL) and those who do not. The application functions both as a traditional chat application and as a bidirectional translator (Sign-to-Text and Text-to-Sign).

## ✨ Key Features
*   **Real-time Chat Interface:** Built with React and Socket.io for instantaneous messaging.
*   **Bidirectional Translation:** 
    *   **Sign-to-Text:** Uses an LSTM Neural Network and MediaPipe to convert recorded sign language gestures into text.
    *   **Text-to-Sign:** Parses English/Hinglish text using NLP (spaCy/NLTK) and translates it into ISL grammatical structure (Subject-Object-Verb), playing the corresponding sign language videos.
*   **Strict Offline Capability:** The NLP and translation engines (Argos Translate) are configured to run entirely offline, ensuring privacy and reliability.
*   **Hinglish Support:** Automatically detects and normalizes Hinglish (Roman Hindi) text, translating it for the backend pipeline.
*   **Dockerized Deployment:** Fully containerized using Docker and `docker-compose` for easy deployment.

## 🛠️ Technology Stack
*   **Frontend:** React 19, Vite, Socket.io-client, CSS
*   **Backend:** Python, Flask, Flask-SocketIO, Gunicorn/Gevent
*   **Database:** MySQL
*   **Machine Learning / CV:** PyTorch (LSTM), MediaPipe (Hand/Pose Landmarks), OpenCV
*   **NLP:** Argos Translate, spaCy, NLTK

## 🚀 Getting Started

### Prerequisites
*   Docker and Docker Compose
*   Python 3.10+ (If running locally)
*   MySQL Server

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yuvi284/sign-language-translator.git
   ```
2. Set up environment variables:
   Copy `.env.example` to `.env` and fill in your database credentials.
3. Start the application using Docker:
   ```bash
   docker-compose up --build
   ```

## 🧠 Machine Learning Architecture
*   **Pose Extraction:** `inference_lstm_sentence.py` extracts spatial coordinates from video frames using MediaPipe.
*   **Temporal Segmentation:** The system calculates frame-by-frame pixel differences to segment continuous videos into distinct words/signs.
*   **Sliding Window Inference:** Segments are passed through a sliding window mechanism into the `SignLanguageLSTM` model to predict sentences with confidence voting.

## 🤝 Contributing
Contributions are welcome! Please fork the repository and submit a pull request.
