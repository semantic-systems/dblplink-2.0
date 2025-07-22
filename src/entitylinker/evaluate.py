import json
import requests


# -------------------
# Configuration
# -------------------
API_URL = "http://localhost:5002/link_entities"
DATASET_FILE = "dblp_quad/questions_test.json"


# -------------------
# Metrics storage
# -------------------
f1_total = 0.0
mrr_total = 0.0
hits_at_1_total = 0.0
hits_at_5_total = 0.0
hits_at_10_total = 0.0
total_gold_entities = 0  # counts gold entities, not questions
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
        if entry.get('type') in {'person', 'publication'}:
            if entry.get('result'):
                first_result = entry['result'][0]
                if first_result[1]:
                    uri = '<' + first_result[1][0] + '>'
                    top_uris.add(uri)
    return list(top_uris)


def extract_all_candidate_uris_per_span(api_response):
    """
    For MRR / Hits@k: Collect **all candidates** for each mention/span.
    """
    results = api_response.get('entitylinkingresults', [])
    candidate_lists = []
    for entry in results:
        if entry.get('type') in {'person', 'publication'}:
            candidates = []
            for res in entry.get('result', []):
                if res[1]:
                    uri = '<' + res[1][0] + '>'
                    candidates.append(uri)
            if candidates:
                candidate_lists.append(candidates)
    return candidate_lists


def compute_f1(predicted_uris, gold_uris):
    pred_set = set(predicted_uris)
    gold_set = set(gold_uris)

    true_positive = len(pred_set & gold_set)
    precision = true_positive / len(pred_set) if pred_set else 0.0
    recall = true_positive / len(gold_set) if gold_set else 0.0

    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def compute_mrr(candidate_lists, gold_uris):
    reciprocal_ranks = []

    for gold in gold_uris:
        found = False
        best_rank = float('inf')

        for candidates in candidate_lists:
            try:
                rank = candidates.index(gold) + 1
                if rank < best_rank:
                    best_rank = rank
                    found = True
            except ValueError:
                continue

        if found:
            reciprocal_ranks.append(1.0 / best_rank)
        else:
            reciprocal_ranks.append(0.0)

    if reciprocal_ranks:
        return sum(reciprocal_ranks) / len(reciprocal_ranks)
    else:
        return 0.0


def compute_hits_at_k(candidate_lists, gold_uris, k):
    hits = 0
    for gold in gold_uris:
        hit_found = False
        for candidates in candidate_lists:
            if gold in candidates[:k]:
                hit_found = True
                break
        if hit_found:
            hits += 1
    return hits / len(gold_uris) if gold_uris else 0.0


# -------------------
# Main Evaluation
# -------------------

with open(DATASET_FILE, 'r') as f:
    dataset = json.load(f)

for example in dataset['questions'][:100]:  # limit for testing
    question = example["question"]["string"]
    gold_entities = example["entities"]  # list of URIs
    print("total_questions:", total_questions + 1)
    print("question:", question)
    print("gold_entities:", gold_entities)

    response = requests.post(API_URL, json={"question": question})#, "text_match_only": True})
    api_response = response.json()

    predicted_uris = extract_top_uris_per_span(api_response)
    candidate_lists = extract_all_candidate_uris_per_span(api_response)

    print("predicted_uris (top prediction per span):", predicted_uris)
    print("candidate_lists (all candidates per span):", candidate_lists)

    # Compute F1
    f1 = compute_f1(predicted_uris, gold_entities)
    f1_total += f1
    print(f"F1 for this question: {f1:.4f}")

    # Compute MRR
    mrr = compute_mrr(candidate_lists, gold_entities)
    mrr_total += mrr
    print(f"MRR for this question: {mrr:.4f}")

    # Compute Hits@k
    hits1 = compute_hits_at_k(candidate_lists, gold_entities, 1)
    hits5 = compute_hits_at_k(candidate_lists, gold_entities, 5)
    hits10 = compute_hits_at_k(candidate_lists, gold_entities, 10)

    hits_at_1_total += hits1 * len(gold_entities)
    hits_at_5_total += hits5 * len(gold_entities)
    hits_at_10_total += hits10 * len(gold_entities)
    total_gold_entities += len(gold_entities)

    total_questions += 1
    print(f"Running F1:  {f1_total / total_questions:.4f}")
    print(f"Running MRR: {mrr_total / total_questions:.4f}")
    print(f"Running Hits@1:  {hits_at_1_total / total_gold_entities:.4f}")
    print(f"Running Hits@5:  {hits_at_5_total / total_gold_entities:.4f}")
    print(f"Running Hits@10: {hits_at_10_total / total_gold_entities:.4f}")
    print("==========================")


# -------------------
# Report Final Results
# -------------------
final_f1 = f1_total / total_questions
final_mrr = mrr_total / total_questions
final_hits1 = hits_at_1_total / total_gold_entities
final_hits5 = hits_at_5_total / total_gold_entities
final_hits10 = hits_at_10_total / total_gold_entities

print("\nEvaluation Results:")
print(f"F1:       {final_f1:.4f}")
print(f"MRR:      {final_mrr:.4f}")
print(f"Hits@1:   {final_hits1:.4f}")
print(f"Hits@5:   {final_hits5:.4f}")
print(f"Hits@10:  {final_hits10:.4f}")
