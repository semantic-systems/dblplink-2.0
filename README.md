
# DBLP-Link-2.0 



This repository contains all code and resources for the Demo Paper accepted at International Semantic Web Conference 2025. The paper is titled "DBLPLink 2.0 -- An Entity Linker for the DBLP Scholarly Knowledge Graph" - Debayan Banerjee, Tilahun Abedissa Taffa, Ricardo Usbeck 



## Setup

### 1. Clone the repository

```bash
git clone git@github.com:semantic-systems/dblplink-2.0.git
cd dblplink-2.0/
```

2. Create virtual environment (recommended)
```bash
python3 -m venv .
source bin/activate  
```

3. Install requirements
```bash
pip install -r requirements.txt
```
4. Run backend
```
cd src/entitylinker
CUDA_VISIBLE_DEVICES=1 python non-streaming-api.py 5002
```

5. Run frontend
```
FRONTEND_CMD="next dev -H 0.0.0.0 -p 3001" reflex run --frontend-port 3001 --backend-port 8001 --env prod
```

Further instructions regarding setting up of a local DBLP SPARQL endpoint and the label Elasticsearch index are currently missing, and will be made available soon. Please contact debayan.banerjee AT leuphana DOT de.
