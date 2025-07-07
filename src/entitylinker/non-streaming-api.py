from flask import Flask, request, jsonify
from entitylinker.entity_linker import EntityLinker
import traceback

# Load configuration
config = {
    "elasticsearch": "http://localhost:9222",
    "sparql_endpoint": "http://localhost:8897/sparql"
}

# Initialize EntityLinker once
entity_linker = EntityLinker(config)

app = Flask(__name__)


@app.route("/get_spans", methods=["POST"])
def get_spans():
    data = request.get_json()
    text = data.get("question")

    if not text:
        return jsonify({"error": "Missing 'question' field in JSON body"}), 400
    try:
        spans = entity_linker.detect_spans_types(text)
        return jsonify(spans)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/get_candidates", methods=["POST"])
def get_candidates():
    data = request.get_json()
    text = data.get("question")
    spans = data.get("spans")

    if not text:
        return jsonify({"error": "Missing 'question' field in JSON body"}), 400
    if not spans:
        return jsonify({"error": "Missing 'spans' field in JSON body"}), 400

    try:
        candidate_results = entity_linker.fetch_candidates(text, spans)
        entity_candidates = []
        for candidate in candidate_results:
            uris = [(item['_id'], item['_source']['label'], item['_source']['type']) for item in candidate]
            entity_candidates.append(uris)
        return jsonify(entity_candidates)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/get_final_result", methods=["POST"])
def get_final_result():
    data = request.get_json()
    text = data.get("question")
    spans = data.get("spans")
    entity_candidates = data.get("entity_candidates")

    if not text:
        return jsonify({"error": "Missing 'question' field in JSON body"}), 400
    if not spans:
        return jsonify({"error": "Missing 'spans' field in JSON body"}), 400
    if not entity_candidates:
        return jsonify({"error": "Missing 'entity_candidates' field in JSON body"}), 400

    try:
        final_result = entity_linker.rerank_candidates(text, spans, entity_candidates)
        print("Final Result:", final_result)
        return jsonify(final_result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/link_entities", methods=["POST"])
def link_entities():
    data = request.get_json()
    text = data.get("question")
    text_match_only = data.get("text_match_only", False) 

    if not text:
        return jsonify({"error": "Missing 'question' field in JSON body"}), 400

    try:
        spans = entity_linker.detect_spans_types(text)
        candidate_results = entity_linker.fetch_candidates(text, spans)

        entity_candidates = []
        for candidate in candidate_results:
            uris = [(item['_id'], item['_source']['label'], item['_source']['type']) for item in candidate]
            entity_candidates.append(uris)

        # Pass the new flag to rerank_candidates
        final_result = entity_linker.rerank_candidates(text, spans, entity_candidates, text_match_only=text_match_only)
        return jsonify(final_result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)

