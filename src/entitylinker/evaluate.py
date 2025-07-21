import json
import requests
from tqdm import tqdm

# -------------------
# Configuration
# -------------------
API_URL = "http://localhost:5002/link_entities"
DATASET_FILE = "dblp_quad/questions_test.json"


# -------------------
# Metrics storage
# -------------------
f1_total = 0.0
total_questions = 0


# -------------------
# Helper functions
# -------------------

def extract_top_uris_per_span(api_response):
    """
    For F1: Only the top prediction for each mention/span.
    """
    results = api_response.get('entitylinkingresults', [])
    top_uris = set()
    for entry in results:
        if entry.get('type') == 'person' or entry.get('type') == 'publication':
            if entry.get('result'):
                first_result = entry['result'][0]
                if first_result[1]:
                    uri = '<' + first_result[1][0] + '>'
                    top_uris.add(uri)
    return list(top_uris)


def compute_f1(predicted_uris, gold_uris):
    pred_set = set(predicted_uris)
    gold_set = set(gold_uris)

    true_positive = len(pred_set & gold_set)
    precision = true_positive / len(pred_set) if pred_set else 0.0
    recall = true_positive / len(gold_set) if gold_set else 0.0

    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


# -------------------
# Main Evaluation
# -------------------

with open(DATASET_FILE, 'r') as f:
    dataset = json.load(f)

for example in dataset['questions']:
    question = example["question"]["string"]
    gold_entities = example["entities"]  # list of URIs
    question = example["question"]["string"]
    print("total_questions:", total_questions+1)
    print("question:", question)
    gold_entities = example["entities"]  # list of URIs
    print("gold_entities:", gold_entities)
    # Query the API
    response = requests.post(API_URL, json={"question": question})#, "text_match_only": True})
    api_response = response.json()
    predicted_uris = extract_top_uris_per_span(api_response)
    print("predicted_uris:", predicted_uris)
    # Compute F1
    f1_total += compute_f1(predicted_uris, gold_entities)
    total_questions += 1
    print(f"F1:  {f1_total/total_questions:.4f}")
    print("==========================")

# -------------------
# Report Final Result
# -------------------
f1 = f1_total / total_questions
print("\nEvaluation Results:")
print(f"F1: {f1:.4f}")
