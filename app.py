from flask import Flask, render_template, request, jsonify
# import rdflib
# from owlready2 import *

app = Flask(__name__)

# --- ROUTE: Serve the Frontend UI ---
@app.route('/')
def home():
    # Flask automatically looks in the 'templates' folder for this file
    return render_template('index.html')

# --- API ENDPOINT: Run SPARQL Queries ---
@app.route('/api/query', methods=['POST'])
def run_query():
    data = request.json
    sparql_query = data.get('query')
    
    # TODO: Connect RDFLib here later to actually process the sparql_query
    print(f"Received SPARQL Query:\n{sparql_query}")
    
    # Returning mock data so the frontend doesn't crash while we build
    mock_response = {
        "results": [
            {"item": "http://example.org/logistics#Shipment_102", "location": "http://example.org/logistics#Truck_B"}
        ]
    }
    return jsonify(mock_response)

# --- API ENDPOINT: Get OWL Inference Alerts ---
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    # TODO: Run Owlready2 reasoner here to find conflicts
    
    mock_alerts = [
        {"type": "conflict", "message": "Shipment_102 requires cooling, but Truck_B has none."}
    ]
    return jsonify(mock_alerts)

if __name__ == '__main__':
    # Runs locally on port 5000 with auto-reload enabled
    app.run(debug=True, port=5000)