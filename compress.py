import re
import contractions

# Shorthand dictionary
shorthand_dict = {
    # Greetings
    "hlo": "hello",
    "hi": "hello",
    "hey": "hello",
    "gm": "good morning",
    "gn": "good night",
    "tc": "take care",
    "bye": "goodbye",

    # Questions
    "whtsp": "whatsapp",
    "hw": "how",
    "wru": "where are you",
    "brb": "be right back",
    "idk": "I don't know",
    "btw": "by the way",
    "wyd": "what are you doing",
    "hbu": "how about you",
    "sup": "what's up",
    "wya": "where you at",
    "ikr": "I know, right",
    "wdym": "what do you mean",
    "np": "no problem",
    "nvm": "never mind",

    # Responses
    "omw": "on my way",
    "ty": "thank you",
    "thx": "thanks",
    "yw": "you're welcome",
    "k": "okay",
    "kk": "okay",
    "ohk": "okay",
    "ye": "yes",
    "nah": "no",
    "ya": "yes",

    # Abbreviations for phrases
    "u": "you",
    "ur": "your",
    "r": "are",
    "b4": "before",
    "l8r": "later",
    "pls": "please",
    "plz": "please",
    "msg": "message",
    "txt": "text",
    "lol": "laughing out loud",
    "rofl": "rolling on the floor laughing",
    "lmao": "laughing my ass off",
    "smh": "shaking my head",
    "afaik": "as far as I know",
    "imho": "in my humble opinion",
    "imo": "in my opinion",
    "asap": "as soon as possible",
    "fyi": "for your information",
    "ttyl": "talk to you later",
    "idc": "I don't care",
    "ily": "I love you",
    "ilu": "I love you",
    "omg": "oh my god",
    "wth": "what the heck",
    "wtf": "what the f***",
    "tbh": "to be honest",
    "idgaf": "I don't give a f***",

    # Time-related
    "tmr": "tomorrow",
    "tmrw": "tomorrow",
    "yday": "yesterday",
    "b4": "before",

    # Social/General
    "bff": "best friends forever",
    "bae": "before anyone else",
    "gf": "girlfriend",
    "bf": "boyfriend",
    "fam": "family",
    "dnd": "do not disturb",
    "jk": "just kidding",
    "xoxo": "hugs and kisses",
    "gg": "good game",
    "rip": "rest in peace",
    "g2g": "got to go",
    "icymi": "in case you missed it",
    "irl": "in real life",
    "bday": "birthday",
    "hbd": "happy birthday",

    # Internet Slang
    "gr8": "great",
    "l8": "late",
    "afk": "away from keyboard",
    "brb": "be right back",
    "roflmao": "rolling on the floor laughing my ass off",
    "tyt": "take your time",
    "ilysm": "I love you so much",
    "tldr": "too long, didn't read",
    "pog": "play of the game",
    "sus": "suspicious",
    "noob": "beginner",
    "ez": "easy",
    "yolo": "you only live once",
    "sry": "sorry",

    # Emotions
    "omfg": "oh my f***ing god",
    "smol": "small",
    "hbd": "happy birthday",
    "hf": "have fun",
    "np": "no problem",
    "idk": "I don't know",
    "pov": "point of view",

    # Miscellaneous
    "gud": "good",
    "nyc": "nice",
    "gn": "good night",
    "bt": "but",
    "abt": "about",
    "bcz": "because",
    "gng": "going",
    "fr": "for real",
    "ikr": "I know, right",
    "rn": "right now",
    "wdym": "what do you mean",
    "coz": "because",
    "tho": "though",
    "ttys": "talk to you soon",
}

# Function to expand shorthand words
def expand_shorthand(sentence):
    words = sentence.split()
    expanded_words = [shorthand_dict.get(word.lower(), word) for word in words]
    return " ".join(expanded_words)

# Function to expand contractions using contractions library
def expand_contractions_with_library(sentence):
    return contractions.fix(sentence)

# Handle incorrectly formatted words (like "donot" -> "do not")
def handle_incorrect_spacing(sentence):
    # Handle common "donot" -> "do not" patterns
    sentence = re.sub(r'\b(donot|doesnot|didnot)\b', lambda match: match.group(0).replace("donot", "do not").replace("doesnot", "does not").replace("didnot", "did not"), sentence)
    return sentence

# Combined function to process a sentence
def compress_sentence(sentence):
    # Step 1: Handle incorrectly formatted words
    sentence = handle_incorrect_spacing(sentence)
    
    # Step 2: Expand shorthand
    sentence = expand_shorthand(sentence)
    
    # Step 3: Expand contractions
    sentence = expand_contractions_with_library(sentence)
    
    return sentence

# Example usage
def main():
    sentence = "hlo, I can't believe she's gng to the party and won't msg u b4 tmr!"
    expanded_sentence = compress_sentence(sentence)
    print(expanded_sentence)

if __name__ == "__main__":
    main()
