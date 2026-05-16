import os
from groq import Groq
import json
from dotenv import load_dotenv

load_dotenv()

# 1. Setup Client (Get key from console.groq.com)
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    print("Warning: GROQ_API_KEY not found in environment variables.")

client = Groq(
    api_key=api_key, 
)

def process_gesture(prediction_data):
    """
    Takes a list of prediction data (list of lists of tuples) and returns a coherent sentence.
    
    Args:
        prediction_data: List of positions, where each position is a list of (word, confidence) tuples.
                         Example: [[("hi", 90), ("hey", 10)], [("there", 80), ...]]
    
    Returns:
        str: The corrected sentence.
    """
    
    if not prediction_data:
        return ""

    try:
        # 3. Format data into a string for the LLM
        formatted_input = ""
        for i, preds in enumerate(prediction_data):
            # Check structure: preds should be list of [word, score] or just word strings?
            # The test.py example used tuples: [("goodbye", 65), ("chair", 30)...]
            # Verify what frontend sends. The `process_uploaded_video` in app.py returns 
            # `[{'word': '...', 'candidates': [...]}, ...]` or simple list?
            # app.py line 450: `return jsonify({'sentence': pred_sentence, 'raw_data': sentence_list})`
            # `sentence_list` variable in `app.py` comes from `recognizer.start()`.
            # We need to be careful about the format.
            # Assuming the frontend sends back exactly what it received in `raw_data`.
            
            # Let's handle the format robustly.
            # If preds is a list of dicts (from candidates), extract word/score.
            # If preds is list of tuples, use as is.
            
            options_str = []
            
            # If it's a list (which it should be for candidates at a position)
            if isinstance(preds, list):
                for item in preds:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        word, score = item[0], item[1]
                        if(score>20):
                            options_str.append(f"{word} ({score}%)")
                    elif isinstance(item, dict) and 'word' in item and 'confidence' in item:
                        options_str.append(f"{item['word']} ({item['confidence']}%)")
                    elif isinstance(item, str):
                        options_str.append(item)
            
            if options_str:
                formatted_input += f"Position {i+1}: [{', '.join(options_str)}]\n"

        if not formatted_input:
            return "Could not format input data."

        print("Sending to LLM:\n" + formatted_input)

        # 4. Call the LLM
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a Sign Language translator. You receive a list of potential words for each position in a sentence, along with confidence scores. Choose the word from each position that creates the most coherent, grammatical English sentence. If the highest scoring word fits, use it. If it creates nonsense, pick the next best option that makes sense. Output ONLY the final sentence. if there are less words than expected, output the sentence as it is."
                },
                {
                    "role": "user",
                    "content": formatted_input
                }
            ],
            temperature=0.1, # Keep strictly factual/logical
        )

        # 5. Result
        final_sentence = completion.choices[0].message.content
        return final_sentence.strip()

    except Exception as e:
        print(f"Error in process_gesture: {e}")
        return None