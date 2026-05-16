import json
import spacy
import mysql.connector
from collections import defaultdict
from nltk.corpus import wordnet as wn
from nltk.stem import PorterStemmer
import re
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
import os
from compress import compress_sentence
from nltk.corpus import wordnet
from googletrans import Translator
# import pickle
# import cv2


# Global variables removed
# all_combined_outputs = []
# video_label = ""
# start_text = ""

# Load NLP models and resources
nlp = spacy.load("en_core_web_sm")
stemmer = PorterStemmer()
lemmatizer = WordNetLemmatizer()

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'db.dev.erp.mdi'),
    'user': os.environ.get('DB_USER', 'phpdev'),
    'password': os.environ.get('DB_PASSWORD', 'phpdev'),
    'database': os.environ.get('DB_NAME', 'phpdevs')
}

class TranslationHandler:
    def __init__(self):
        self.multi_word_expressions = self.load_multiword_expressions('multiword_expressions.json')

    @staticmethod
    def load_multiword_expressions(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)

    @staticmethod
    def get_synonyms(tokens, pos_filter=None):
        synonyms = defaultdict(set)
        for token in tokens:
            for syn in wn.synsets(token, pos=pos_filter):
                for lemma in syn.lemmas():
                    if lemma.name() != token:
                        synonyms[token].add(lemma.name())
        return synonyms

    def process_sentence(self, sentence):
        
        print(f"\nProcessing Sentence: {sentence}")
        processed_text = TextProcessor.preprocess_text(sentence)
        print(processed_text)
        expanded_text = TextProcessor.expand_multiword_expressions(processed_text, self.multi_word_expressions)
        print(expanded_text)
        tokens, _ = TextProcessor.tokenize_text(expanded_text)

        # Preserve original token order for ISL playback and only strip
        # helper/filler words instead of reordering by parts of speech.
        isl_sentence = TextProcessor.normalize_for_isl(tokens, set(self.multi_word_expressions.keys()))
        print("all_combined_outputs", isl_sentence)
        return isl_sentence

    def create_indexed_list_with_duplicates(self, isl_sentence):
        print("all_combined_outputs",isl_sentence)
        return [(index, word) for index, word in enumerate(isl_sentence)]

    def create_indexed_list_with_duplicates_simple(self, simplified_text):
        return [(index, word) for index, word in enumerate(simplified_text)]
    
class TextProcessor:
    @staticmethod
    def preprocess_text(text):
        text = text.lower()
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def expand_multiword_expressions(text, expressions):
        print("hello")
        for phrase, token in expressions.items():
            text = re.sub(r'\b' + re.escape(phrase) + r'\b', token, text)
        return text

    @staticmethod
    def tokenize_text(text):
        doc = nlp(text)
        # Keep original token order intact here. ISL-specific filtering happens
        # later in normalize_for_isl(); dropping tokens here loses playable words
        # such as "name" before lookup even begins.
        tokens = [token.text.lower() for token in doc if not token.is_punct]

        return tokens, doc

    @staticmethod
    def eliminate_gerunds(tokens, multiword_tokens):
        result = []
        for token in tokens:
            if token in multiword_tokens or not token.endswith('ing'):
                result.append(token)
            else:
                result.append(stemmer.stem(token[:-3]))
        return result

    @staticmethod
    def normalize_for_isl(tokens, multiword_tokens):
        helping_verbs = {
            "am", "is", "are", "was", "were", "be", "being", "been",
            "have", "has", "had", "do", "does", "did", "can", "could",
            "will", "would", "shall", "should", "may", "might", "must"
        }
        extra_words = {
            "to", "for", "at", "by", "from", "in", "into", "of", "since",
            "through", "till", "until", "via", "within", "a", "an", "the",
            "and", "but", "or", "nor", "so", "yet", "because", "if", "although"
        }

        normalized = []
        gerund_fixed = TextProcessor.eliminate_gerunds(tokens, multiword_tokens)

        for token in gerund_fixed:
            if token in multiword_tokens:
                normalized.append(token)
                continue

            lowered = token.lower()
            if len(lowered) == 1 and lowered.isalpha():
                normalized.append(lowered)
                continue

            if lowered in helping_verbs or lowered in extra_words:
                continue

            normalized.append(lemmatizer.lemmatize(lowered, wordnet.VERB))

        return normalized

    @staticmethod
    def extract_parts_of_speech(doc):
        subjects, nouns, pronouns, objects, verbs, adjectives, adverbs, interrogatives, negations, interjections = [], [], [], [], [], [], [], [], [], []

        for i, token in enumerate(doc):
            token_text = token.text if "_" in token.text else token.lemma_

            if token.dep_ in ("nsubj", "nsubjpass"):
                subjects.append(token_text)
            elif token.dep_ in ("dobj", "obj"):
                objects.append(token_text)
            elif token.pos_ == "VERB" and token.dep_ != "aux":
                verbs.append(token_text)
            elif token.pos_ == "ADJ" or token.dep_ == "amod":
                adjectives.append(token_text)
            elif token.pos_ in ("NOUN", "PROPN"):
                nouns.append(token_text)
            elif token.pos_ == "PRON":
                pronouns.append(token_text)
            elif token.pos_ == "ADV":
                adverbs.append(token_text)
            elif token.text.lower() == "not":
                negations.append("not")
            elif token.tag_ in {"WRB", "WP", "WDT"}:
                interrogatives.append(token_text)
            elif token.pos_ == "INTJ":
                interjections.append(token_text)

        return subjects, nouns, pronouns, objects, verbs, adjectives, adverbs, interrogatives, negations, interjections

    @staticmethod
    def apply_isl_grammar_rules(*parts_of_speech):
        return [word for part in parts_of_speech for word in part]

    @staticmethod
    def get_base_form(word, pos_tag):
        if word.lower() in ['is', 'am', 'are', 'was', 'were', 'has', 'have', 'in', 'the', 'and']:
            return ''
        if pos_tag.startswith('VB'):
            return lemmatizer.lemmatize(word, wordnet.VERB)
        return word

    @staticmethod
    def simplify_sentence(sentence):
        sentence = sentence.strip()
        simplified_tokens = []
        tokens = word_tokenize(sentence)
        tagged_tokens = nltk.pos_tag(tokens)

        for word, tag in tagged_tokens:
            if word in [',', '.', '!', '?', ';', ':']:
                continue
            base_word = TextProcessor.get_base_form(word, tag)
            if base_word:
                simplified_tokens.append(base_word.lower())

        return simplified_tokens

    @staticmethod
    def remove_extra_words(sentence):
        helping_verbs = {"am", "is", "are", "was", "were", "be", "being", "been", "have",
                        "has", "had", "does", "did", "can", "could", "will",
                        "would", "shall", "should", "may", "might", "must"}
        extra_words = {"to", "for", "at", "by", "from", "in", "into", "of", "since",
                      "through", "till", "until", "via", "within", "a", "an", "the",
                      "and", "but", 'or', 'nor', 'so', 'yet', 'because', 'if', "although"}

        words = re.findall(r"\w+", sentence.lower())
        filtered_words = [
            word for word in words
            if word not in helping_verbs and word not in extra_words
        ]
        simplified = " ".join(filtered_words)

        if len(simplified) > 0:
            simplified = simplified[0].upper() + simplified[1:]
        return simplified if simplified else "[Sentence reduced to nothing]"

    @staticmethod
    def convert_to_simple_sentences(text):
        text = TextProcessor.remove_extra_words(text)
        sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)
        all_simplified_tokens = []

        for sentence in sentences:
            simplified_tokens = TextProcessor.simplify_sentence(sentence)
            all_simplified_tokens.extend(simplified_tokens)

        return all_simplified_tokens

    @staticmethod
    def split_sentence(sentence):
        pattern = r"(?<=\.|\!|,)(?=\s|$)"
        sentence_parts = re.split(pattern, sentence)
        return [part.strip() for part in sentence_parts if part.strip()]
    
class DatabaseHandler:
    @staticmethod
    def connect_to_db():
        return mysql.connector.connect(**DB_CONFIG)

    @staticmethod
    def lookup_word_with_duration(conn, word):
        cursor = conn.cursor()
        try:
            cursor.execute("""SELECT video_path, duration FROM isl_video_dictionary ivd
                            WHERE IF(RIGHT(SUBSTRING_INDEX(video_title, '(', 1), 1) = '_',
                            LEFT(SUBSTRING_INDEX(video_title, '(', 1),
                            LENGTH(SUBSTRING_INDEX(video_title, '(', 1)) - 1),
                            SUBSTRING_INDEX(video_title, '(', 1)) = (%s)""", (word,))
            result = cursor.fetchall()
            if result:
                print("Exact match found:", result)
                return result[0]

            # 2. Fallback - match part of a multi-word title
            print("Fallback triggered for:", word)
            pattern1 = f"\\_{word}\\_%"  # Matches "_too_anything"
            pattern2 = f"%\\_{word}\\_%"  # Matches "anything_too_anything"
            pattern3 = f"%\\_{word}"  # Matches "anything_too"
            pattern4 = f"\\_{word}"  # Matches "_too" (at start)
            pattern5 = f"{word}\\_%"  # Matches "too_" (at end)
            pattern6 = f"{word}"  # Matches exact "too"

            cursor.execute("""
                SELECT video_path, duration
                FROM isl_video_dictionary ivd
                WHERE
                    (LOWER(video_title) LIKE %s OR  /* _too_anything */
                    LOWER(video_title) LIKE %s OR  /* anything_too_anything */
                    LOWER(video_title) LIKE %s OR  /* anything_too */
                    LOWER(video_title) LIKE %s OR  /* _too */
                    LOWER(video_title) LIKE %s OR  /* too_ */
                    LOWER(video_title) = %s)       /* exact too */
            """, (pattern1, pattern2, pattern3, pattern4, pattern5, pattern6))

            result1 = cursor.fetchall()
            print("Fallback results:", result1)

            if result1:
                return result1[0]
            else:
                return None

        finally:
            cursor.close()

    @staticmethod
    def lookup_synonym_with_duration(conn, synonym):
        cursor = conn.cursor()
        try:
            cursor.execute("""SELECT video_path, duration FROM isl_video_dictionary ivd
                            WHERE IF(RIGHT(SUBSTRING_INDEX(video_title, '(', 1), 1) = '_',
                            LEFT(SUBSTRING_INDEX(video_title, '(', 1),
                            LENGTH(SUBSTRING_INDEX(video_title, '(', 1)) - 1),
                            SUBSTRING_INDEX(video_title, '(', 1)) = (%s)""", (synonym,))
            result = cursor.fetchall()
            return result[0] if result else None
        finally:
            cursor.close()

    @staticmethod
    def lookup_alphabet_videos_from_db(conn, word):
        alphabet_videos = []    
        for char in word:       
            if char.isalpha():
                video_data = DatabaseHandler.lookup_word_with_duration(conn, char.lower())
                if video_data:
                    video_path, duration = video_data
                    alphabet_videos.append((video_path, duration))
        return alphabet_videos

    @staticmethod
    def save_translation(input_text, output_text):
        conn = DatabaseHandler.connect_to_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO translation_logs (input_text, output_text) VALUES (%s, %s)",
                          (input_text, output_text))
            conn.commit()
        except Exception as e:
            print(f"Error saving translation: {e}")
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def fetch_translations_from_db():
        conn = DatabaseHandler.connect_to_db()
        cursor = conn.cursor()
        translations = []

        try:
            cursor.execute("""SELECT id, input_text, output_text, timestamp
                            FROM translation_logs ORDER BY timestamp DESC""")
            results = cursor.fetchall()

            for result in results:
                if len(result) == 4:
                    id, input_text, output_text, timestamp = result
                    date_value = timestamp.strftime('%Y-%m-%d')
                    time_value = timestamp.strftime('%H:%M:%S')

                    translations.append({
                        'id': id,
                        'input': input_text,
                        'output': output_text,
                        'date': date_value,
                        'time': time_value
                    })

        except mysql.connector.Error as err:
            print(f"Error fetching translations from DB: {err}")
        finally:
            cursor.close()
            conn.close()

        return translations

    @staticmethod
    def save_feedback(translation_id, feedback):
        conn = DatabaseHandler.connect_to_db()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE translation_logs SET feedback = %s WHERE id = %s",
                         (feedback, translation_id))
            conn.commit()
        except Exception as e:
            print(f"Database error: {str(e)}")
            return False
        finally:
            cursor.close()
            conn.close()
        return True
