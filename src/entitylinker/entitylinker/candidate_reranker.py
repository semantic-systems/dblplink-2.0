import json
import requests
from typing import List, Tuple
from urllib.parse import urlencode
import sys
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, LogitsProcessorList
import torch.nn.functional as F
import numpy as np
import time

class CandidateReranker:
    def __init__(self, model, tokenizer, config, device="cuda"):
        self.config = config
        self.endpoint = config["sparql_endpoint"]
        self.headers = {
            "Accept": "application/sparql-results+json"
        }
        self.tokenizer = tokenizer
        self.model = model
        self.device = device

    def format_input(self, mention, context, entity_name, entity_info_line):
        entity_info_text = entity_info_line
        #print(entity_info_text)
        return (
        f"You are an assistant linking mentions to entities.\n"
        f"Document: {context}\n"
        f"Mention: {mention}\n"
        f"Candidate Entity: {entity_name}\n"
        f"Entity Info: {entity_info_text}\n"
        f"Question: Does the mention belong to this entity? Answer: yes/no\n"
        f"Answer:"
    )
    def compute_avg_yes_score(self, mention, context, entity_name, entity_info_lines):
        """
        Computes the average log-probability score for 'yes' as the next token
        over all entity_info_lines.
        Returns the average score and the top contributing sentence.
        """
        # Important: do NOT include 'yes' in the prompt
        full_inputs = [self.format_input(mention, context, entity_name, line) for line in entity_info_lines]
        inputs = self.tokenizer(full_inputs, return_tensors='pt', padding=True, truncation=True, max_length=128).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits  # (batch_size, seq_len, vocab_size)

        log_probs = F.log_softmax(logits, dim=-1)
        yes_token_id = self.tokenizer("yes", add_special_tokens=False)["input_ids"][0]

        scores = []
        for i in range(len(full_inputs)):
            # Length of the input without padding
            attention_mask = inputs.attention_mask[i]
            input_len = attention_mask.sum().item()

            # Log-probability of 'yes' as the next token
            yes_logprob = log_probs[i, input_len - 1, yes_token_id].item()
            scores.append(yes_logprob)

        avg_score = float(np.mean(scores))
        best_index = scores.index(max(scores))
        best_sentence = entity_info_lines[best_index]
        return avg_score, best_sentence

    def fetch_one_hop(self, entity_uri):
        """
        Fetch one-hop neighbors (both subject and object) and their labels.
        Returns two lists of dictionaries with ?sLabel ?pLabel ?oLabel
        """
        headers = {
            "Accept": "application/sparql-results+json"
        }

        queryleft = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>
        PREFIX dblp: <https://dblp.org/rdf/schema#>

        SELECT DISTINCT ?sLabel ?p ?oLabel WHERE {{
            VALUES ?s {{ <{entity_uri[0]}> }}
            ?s ?p ?o .
            OPTIONAL {{ ?s rdfs:label|skos:prefLabel|dc:title|foaf:name|dblp:abstract|dc:description|dblp:title ?sLabel }}
            OPTIONAL {{ ?p rdfs:label|skos:prefLabel|dc:title|foaf:name|dblp:abstract|dc:description|dblp:title ?pLabel }}
            OPTIONAL {{ ?o rdfs:label|skos:prefLabel|dc:title|foaf:name|dblp:abstract|dc:description|dblp:title ?oLabel }}
            FILTER (?p NOT IN (dblp:signatureCreator,dblp:signaturePublication,dblp:hasSignature))
        }} LIMIT 30
        """
        queryright = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>
        PREFIX dblp: <https://dblp.org/rdf/schema#>

        SELECT DISTINCT ?sLabel ?pLabel ?oLabel WHERE {{
            VALUES ?o {{ <{entity_uri[0]}> }}
            ?s ?p ?o .
            OPTIONAL {{ ?s rdfs:label|skos:prefLabel|dc:title|foaf:name|dblp:abstract|dc:description|dblp:title ?sLabel }}
            OPTIONAL {{ ?p rdfs:label|skos:prefLabel|dc:title|foaf:name|dblp:abstract|dc:description|dblp:title ?pLabel }}
            OPTIONAL {{ ?o rdfs:label|skos:prefLabel|dc:title|foaf:name|dblp:abstract|dc:description|dblp:title ?oLabel }}
            FILTER (?p NOT IN (dblp:signatureCreator,dblp:signaturePublication,dblp:hasSignature))
        }} LIMIT 30
        """

        response_left = requests.get(self.endpoint, headers=headers, params={"query": queryleft})
        response_right = requests.get(self.endpoint, headers=headers, params={"query": queryright})

        left_json = response_left.json()
        right_json = response_right.json()

        return left_json, right_json

    
    def linearise_neighbourhood(self, left_json, right_json):
        """
        Linearizes the one-hop neighborhood into a list of strings.
        Each string is a formatted representation of the triple from JSON data.
        """
        def extract_triple(binding, s_key='sLabel', p_key='p', o_key='oLabel'):
            s = binding.get(s_key, {}).get('value', '').strip()
            p = binding.get(p_key, {}).get('value', '').strip()
            o = binding.get(o_key, {}).get('value', '').strip()
            if '_:bn' in s or '_:bn' in o:
                return None
            return f"{s} — {p} — {o}" if s and p and o else None

        triples = []

        for binding in left_json["results"]["bindings"]:
            triple = extract_triple(binding, s_key="sLabel", p_key="p", o_key="oLabel")
            if triple:
                triples.append(triple)

        for binding in right_json["results"]["bindings"]:
            triple = extract_triple(binding, s_key="sLabel", p_key="pLabel", o_key="oLabel")
            if triple:
                triples.append(triple)

        return triples



    def rerank_candidates(self, text, spans, entity_candidates, text_match_only):
        """
        Reranks the candidate entities based on their scores.
        Returns a list of tuples (entity_uri, score) sorted by score.
        """
        final_result = {}
        sorted_spans = []
        if text_match_only:
            print("Text match only mode enabled. Skipping entity reranking.")
            for span, entity_uris in zip(spans, entity_candidates):
                entity_scores = []
                for entity_uri in entity_uris:
                    # Here we assume that the score is 1.0 for text match only
                    # In a real scenario, you might want to compute some score based on text matching
                    entity_scores.append([-1.0, [entity_uri[0], entity_uri[1], entity_uri[2], ""]])
                sorted_spans.append({'label': span['label'], 'result': entity_scores, 'type': span['type']})
        else:
            for span,entity_uris in zip(spans,entity_candidates):
                entity_scores = []
                for entity_uri in entity_uris:
                    print("Fetching one-hop neighbors for entity URI...",entity_uri)
                    start = time.time()
                    left, right = self.fetch_one_hop(entity_uri)
                    end = time.time()
                    print(f"Time taken for neighbourhood: {end - start:.6f} seconds")
                    # Linearize the neighborhood
                    entity_neighborhood = self.linearise_neighbourhood(left, right)
                    if not entity_neighborhood:
                        print(f"No neighborhood found for entity {entity_uri[0]}")
                        continue
                    # Score the entity based on its neighborhood
                    start = time.time()
                    print(f"Scoring entity {entity_uri[0]} with neighborhood size {len(entity_neighborhood)}")
                    #score,sentence = self.compute_max_yes_score(span['label'], text, entity_uri[0], entity_neighborhood)
                    score, evidence_sentence = self.compute_avg_yes_score(span['label'], text, entity_uri[0], entity_neighborhood)
                    end = time.time()
                    print(f"Time taken for sorting: {end - start:.6f} seconds")
                    entity_scores.append([score, [entity_uri[0], entity_uri[1], entity_uri[2], evidence_sentence]]) #0 is url, 1 is label, 2 is type
                # Sort by score in descending order
                entity_scores.sort(key=lambda x: x[0], reverse=True)
                sorted_spans.append({'label': span['label'], 'result': entity_scores, 'type': span['type']})
        final_result['entitylinkingresults'] = sorted_spans
        final_result['predictedlabelspans'] = [span['label'] + ' : ' + span['type'] for span in spans]
        final_result['question'] = text
        # Return the sorted list of entity URIs and their scores    
        return final_result
    

if __name__ == "__main__":
    # Example usage
    config = {
        "sparql_endpoint": "http://localhost:89897/sparql"
    }
    reranker = CandidateReranker(config)
    text = "which papers in neurips was authored by Biemann?"
    spans = [{"type": "person", "label": "Biemann"}, {"type": "venue", "label": "NeurIPS"}]
    entity_candidates = [['https://dblp.org/pid/306/6142' ,'https://dblp.org/pid/20/6100'],['https://dblp.org/streams/conf/gazeml','https://dblp.org/streams/conf/nips']] # Example URIs
    sorted_spans = reranker.rerank_candidates(text, spans, entity_candidates)
    print("Final Reranked Entities:")
    for sorted_span in sorted_spans['entitylinkingresults']:
        print(f"Span: {sorted_span['span']}")
        for entity_uri, score, sentence in sorted_span['entities']:
            print(f"  Entity: {entity_uri}, Score: {score:.4f} Sentence: {sentence}")
    print("Reranking completed.")