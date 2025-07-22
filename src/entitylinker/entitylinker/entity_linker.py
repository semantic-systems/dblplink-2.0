import sys,os,json
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import re
from elasticsearch import Elasticsearch
from entitylinker.candidate_reranker import CandidateReranker
from transformers import BitsAndBytesConfig

# Inside your __init__ of EntityLinker
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,            # Or use `load_in_8bit=True` for 8-bit
    bnb_4bit_quant_type="nf4",    # Normal float 4; more accurate than int
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.float16
)

class EntityLinker:    
    def __init__(self, config):
        self.config = config
        MODEL_NAME = "Qwen/Qwen2.5-3b-Instruct"
        #MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"
        # Load model and tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
                        MODEL_NAME,
                        quantization_config=bnb_config,
                        device_map="auto",
                        trust_remote_code=True
                    ).eval()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        #self.model.to(self.device)
        self.es = Elasticsearch(config['elasticsearch'])
        self.candidate_reranker = CandidateReranker(self.model, self.tokenizer, config, self.device)

    def detect_spans_types(self, text):
        """
        Detects spans in the text and returns their types.
        This is a placeholder implementation.
        """
        messages = [
        {"role": "system", "content": "You are an information extraction assistant."},
        {"role": "user", "content": f"""Extract named entities from the following sentence and classify them into one of the following types: person, publication, venue.
         Let the output be a JSON array of objects with fields 'label' and 'type'.
        Sentence: "{text}"
        Entities:"""}
        ]
        self.tokenizer.pad_token = self.tokenizer.eos_token
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([prompt], return_tensors="pt", padding=True, truncation=True).to(self.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        decoded_outputs = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        output = decoded_outputs[0]
        json_matches = re.findall(r'\[\s*{.*?}\s*]', output, re.DOTALL)
        entities = []
        if json_matches:
            json_str = json_matches[-1]
            try:
                entities = json.loads(json_str)
                print("Extracted entity list:")
                print(json.dumps(entities, indent=2))
            except json.JSONDecodeError as e:
                print("JSON decoding error:", e)
                print("Raw matched text:\n", json_str)
        else:
            print("No JSON array found in model output.")
        # Placeholder for span detection logic
        return entities
    
    def fetch_candidates(self, text, spans):
        """
        Fetches candidate entities for a given span in the text.
        This is a placeholder implementation.
        """
        results = []
        for span in spans:
            entity_type = span['type']
            types = []
            if entity_type == "person":
                types = ["https://dblp.org/rdf/schema#Creator", "https://dblp.org/rdf/schema#Person"]
            elif entity_type == "publication":
                types = ["https://dblp.org/rdf/schema#Book", "https://dblp.org/rdf/schema#Article", "https://dblp.org/rdf/schema#Publication"]
            #elif entity_type == "venue":
            #    types = ["https://dblp.org/rdf/schema#Conference", "https://dblp.org/rdf/schema#Incollection", "https://dblp.org/rdf/schema#Inproceedings", "https://dblp.org/rdf/schema#Journal", "https://dblp.org/rdf/schema#Series", "https://dblp.org/rdf/schema#Stream"]
            elif entity_type == "venue":
                types = ["https://dblp.org/rdf/schema#Stream"]
            
            label = span['label']
            print(f"Fetching candidates for type: {entity_type}, label: {label}")    
            query = {
                "size": 10,
                "query": {
                    "bool": {
                        "must": [
                            {"terms": {"type": types}},   # exact match on type
                            {"match": {"label": label}}        # fuzzy/textual match on label
                        ]
                    }
                }
            }
            response = self.es.search(index='dblp', body=query)
            # Extract entity field from results
            results.append([
                hit
                for hit in response["hits"]["hits"]
            ])
        # Placeholder for candidate fetching logic
        return results
    
    def rerank_candidates(self, text, spans, entity_candidates, text_match_only=False):
        """
        Reranks the candidates based on some criteria.
        This is a placeholder implementation.
        """
        sorted_spans = self.candidate_reranker.rerank_candidates(text, spans, entity_candidates, text_match_only)
        return sorted_spans
    
if __name__ == "__main__":
    # Example usage
    config = {
        "elasticsearch": "http://localhost:9222",
        "sparql_endpoint": "http://localhost:8897/sparql"
    }
    
    entity_linker = EntityLinker(config)
    
    text = "which papers in ACL 2023 was authored by Chris Biemann?"
    print("Detecting spans and types in text:", text)
    spans = entity_linker.detect_spans_types(text)
    print("Detected Spans:", spans)
    print(" Fetching candidates for detected spans...")
    candidate_results = entity_linker.fetch_candidates(text, spans)
    entity_candidates = []
    for candidate in candidate_results:
        uris = []
        for item in candidate:
            uris.append((item['_id'], item['_source']['label'], item['_source']['type']))
        entity_candidates.append(uris)
    print("Candidate Results:", entity_candidates)
    print("sorting candidates ...")
    sorted_spans = entity_linker.rerank_candidates(text, spans, entity_candidates)
    print("Final Reranked Entities:")
    print(json.dumps(sorted_spans, indent=2))
    for sorted_span in sorted_spans['entitylinkingresults']:
        print(f"Span: {sorted_span['label']}")
        print("Entities:")
        for score,entity in sorted_span['result']:
            print(f"  - {entity[0]} {entity[1]}  (Score: {score}) Sentence: {entity[2]}")
            
