import os
from flask import Flask, render_template, request, jsonify
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from rdflib.namespace import RDFS, OWL, XSD

app = Flask(__name__)

# --- NAMESPACE DEFINITION ---
LOGISTICS = Namespace("http://example.org/logistics#")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TTL_PATH = os.path.join(DATA_DIR, "logistics.ttl")
OWL_PATH = os.path.join(DATA_DIR, "logistics.owl")

# --- INITIALIZE AND LOAD GRAPH ---
g = Graph()

def run_inference(graph):
    """
    Performs RDFS-style subClassOf inference and applies custom business
    rules for inventory management, writing resulting alerts back into the graph.
    """
    print("[Inference Engine] Starting inference...")
    
    # 1. RDFS subClassOf Transitive Closure
    # Find all subclasses and trace inheritance paths
    subclass_map = {}
    for s, p, o in graph.triples((None, RDFS.subClassOf, None)):
        subclass_map.setdefault(s, set()).add(o)
        
    changed = True
    while changed:
        changed = False
        for sub, parents in list(subclass_map.items()):
            for parent in list(parents):
                if parent in subclass_map:
                    for gparent in subclass_map[parent]:
                        if gparent not in parents:
                            parents.add(gparent)
                            changed = True
                            
    # Apply inferred types back to the graph (e.g. PerishableItem is also a StockItem)
    inferred_types = []
    for ind, p, t in graph.triples((None, RDF.type, None)):
        if t in subclass_map:
            for parent in subclass_map[t]:
                if (ind, RDF.type, parent) not in graph:
                    inferred_types.append((ind, RDF.type, parent))
                    
    for triple in inferred_types:
        graph.add(triple)
        
    # 2. Clear Existing Inferred Alerts
    # This prevents duplicate alerts when rules are re-evaluated
    alert_classes = [
        LOGISTICS.Alert, 
        LOGISTICS.StorageConflictAlert, 
        LOGISTICS.TransportConflictAlert, 
        LOGISTICS.LowStockAlert, 
        LOGISTICS.CapacityAlert
    ]
    for ac in alert_classes:
        for alert in list(graph.subjects(RDF.type, ac)):
            graph.remove((alert, None, None))
            graph.remove((None, LOGISTICS.hasAlert, alert))
            graph.remove((alert, RDF.type, None))
            
    # 3. Rule-Based Inference: Cooling Storage Validation
    for item in graph.subjects(RDF.type, LOGISTICS.StockItem):
        requires_cooling = graph.value(item, LOGISTICS.requiresCooling)
        if requires_cooling is not None and requires_cooling.toPython() is True:
            facility = graph.value(item, LOGISTICS.storedIn)
            if facility:
                has_cooling = graph.value(facility, LOGISTICS.hasCooling)
                if has_cooling is not None and has_cooling.toPython() is False:
                    alert_id = URIRef(f"{item}_StorageCoolingAlert")
                    item_name = str(graph.value(item, LOGISTICS.itemName) or item.split('#')[-1])
                    fac_name = str(graph.value(facility, LOGISTICS.facilityName) or facility.split('#')[-1])
                    msg = f"Perishable item '{item_name}' requires cold storage, but is stored in '{fac_name}' which lacks cooling."
                    
                    graph.add((alert_id, RDF.type, LOGISTICS.StorageConflictAlert))
                    graph.add((alert_id, LOGISTICS.alertMessage, Literal(msg, datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertSeverity, Literal("High", datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertType, Literal("Storage Cooling Conflict", datatype=XSD.string)))
                    graph.add((item, LOGISTICS.hasAlert, alert_id))
                    graph.add((facility, LOGISTICS.hasAlert, alert_id))

    # 4. Rule-Based Inference: Hazardous Storage Validation
    for item in graph.subjects(RDF.type, LOGISTICS.StockItem):
        is_hazardous = graph.value(item, LOGISTICS.isHazardous)
        if is_hazardous is not None and is_hazardous.toPython() is True:
            facility = graph.value(item, LOGISTICS.storedIn)
            if facility:
                haz_approved = graph.value(facility, LOGISTICS.isHazardousApproved)
                if haz_approved is not None and haz_approved.toPython() is False:
                    alert_id = URIRef(f"{item}_StorageHazardAlert")
                    item_name = str(graph.value(item, LOGISTICS.itemName) or item.split('#')[-1])
                    fac_name = str(graph.value(facility, LOGISTICS.facilityName) or facility.split('#')[-1])
                    msg = f"Hazardous item '{item_name}' is stored in '{fac_name}', which is not approved for hazardous materials."
                    
                    graph.add((alert_id, RDF.type, LOGISTICS.StorageConflictAlert))
                    graph.add((alert_id, LOGISTICS.alertMessage, Literal(msg, datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertSeverity, Literal("Critical", datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertType, Literal("Hazardous Storage Conflict", datatype=XSD.string)))
                    graph.add((item, LOGISTICS.hasAlert, alert_id))
                    graph.add((facility, LOGISTICS.hasAlert, alert_id))

    # 5. Rule-Based Inference: Low Stock Warning
    for item in graph.subjects(RDF.type, LOGISTICS.StockItem):
        qty = graph.value(item, LOGISTICS.quantity)
        min_t = graph.value(item, LOGISTICS.minThreshold)
        if qty is not None and min_t is not None:
            qty_val = qty.toPython()
            min_val = min_t.toPython()
            if qty_val < min_val:
                alert_id = URIRef(f"{item}_LowStockAlert")
                item_name = str(graph.value(item, LOGISTICS.itemName) or item.split('#')[-1])
                msg = f"Stock level for '{item_name}' is low: {qty_val} remaining (minimum threshold is {min_val})."
                
                graph.add((alert_id, RDF.type, LOGISTICS.LowStockAlert))
                graph.add((alert_id, LOGISTICS.alertMessage, Literal(msg, datatype=XSD.string)))
                graph.add((alert_id, LOGISTICS.alertSeverity, Literal("Medium", datatype=XSD.string)))
                graph.add((alert_id, LOGISTICS.alertType, Literal("Low Stock", datatype=XSD.string)))
                graph.add((item, LOGISTICS.hasAlert, alert_id))

    # 6. Rule-Based Inference: Storage Capacity Constraint
    facility_quantities = {}
    for item in graph.subjects(RDF.type, LOGISTICS.StockItem):
        facility = graph.value(item, LOGISTICS.storedIn)
        if facility:
            qty = graph.value(item, LOGISTICS.quantity)
            if qty is not None:
                facility_quantities[facility] = facility_quantities.get(facility, 0) + qty.toPython()
                
    for facility, total_qty in facility_quantities.items():
        cap = graph.value(facility, LOGISTICS.capacity)
        if cap is not None:
            cap_val = cap.toPython()
            if total_qty > cap_val:
                alert_id = URIRef(f"{facility}_CapacityAlert")
                fac_name = str(graph.value(facility, LOGISTICS.facilityName) or facility.split('#')[-1])
                msg = f"Capacity exceeded at '{fac_name}': storing {total_qty} items (limit is {cap_val})."
                
                graph.add((alert_id, RDF.type, LOGISTICS.CapacityAlert))
                graph.add((alert_id, LOGISTICS.alertMessage, Literal(msg, datatype=XSD.string)))
                graph.add((alert_id, LOGISTICS.alertSeverity, Literal("High", datatype=XSD.string)))
                graph.add((alert_id, LOGISTICS.alertType, Literal("Capacity Limit Exceeded", datatype=XSD.string)))
                graph.add((facility, LOGISTICS.hasAlert, alert_id))

    # 7. Rule-Based Inference: Refrigerated Transport Validation
    for item in graph.subjects(RDF.type, LOGISTICS.StockItem):
        requires_cooling = graph.value(item, LOGISTICS.requiresCooling)
        if requires_cooling is not None and requires_cooling.toPython() is True:
            vehicle = graph.value(item, LOGISTICS.assignedTo)
            if vehicle:
                has_cooling = graph.value(vehicle, LOGISTICS.hasVehicleCooling)
                if has_cooling is not None and has_cooling.toPython() is False:
                    alert_id = URIRef(f"{item}_TransportCoolingAlert")
                    item_name = str(graph.value(item, LOGISTICS.itemName) or item.split('#')[-1])
                    veh_name = str(graph.value(vehicle, LOGISTICS.vehicleName) or vehicle.split('#')[-1])
                    msg = f"Perishable item '{item_name}' requires refrigerated transport, but is assigned to '{veh_name}' which lacks cooling."
                    
                    graph.add((alert_id, RDF.type, LOGISTICS.TransportConflictAlert))
                    graph.add((alert_id, LOGISTICS.alertMessage, Literal(msg, datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertSeverity, Literal("High", datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertType, Literal("Transport Cooling Conflict", datatype=XSD.string)))
                    graph.add((item, LOGISTICS.hasAlert, alert_id))
                    graph.add((vehicle, LOGISTICS.hasAlert, alert_id))

    # 8. Rule-Based Inference: Hazardous Transport Validation
    for item in graph.subjects(RDF.type, LOGISTICS.StockItem):
        is_hazardous = graph.value(item, LOGISTICS.isHazardous)
        if is_hazardous is not None and is_hazardous.toPython() is True:
            vehicle = graph.value(item, LOGISTICS.assignedTo)
            if vehicle:
                has_permit = graph.value(vehicle, LOGISTICS.hasHazardousPermit)
                if has_permit is not None and has_permit.toPython() is False:
                    alert_id = URIRef(f"{item}_TransportHazardAlert")
                    item_name = str(graph.value(item, LOGISTICS.itemName) or item.split('#')[-1])
                    veh_name = str(graph.value(vehicle, LOGISTICS.vehicleName) or vehicle.split('#')[-1])
                    msg = f"Hazardous item '{item_name}' requires specialized vehicle transit, but is assigned to '{veh_name}' which lacks a hazardous permit."
                    
                    graph.add((alert_id, RDF.type, LOGISTICS.TransportConflictAlert))
                    graph.add((alert_id, LOGISTICS.alertMessage, Literal(msg, datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertSeverity, Literal("Critical", datatype=XSD.string)))
                    graph.add((alert_id, LOGISTICS.alertType, Literal("Transport Hazard Conflict", datatype=XSD.string)))
                    graph.add((item, LOGISTICS.hasAlert, alert_id))
                    graph.add((vehicle, LOGISTICS.hasAlert, alert_id))

    # Save to TTL (Turtle) and OWL (RDF/XML)
    graph.serialize(destination=TTL_PATH, format="turtle")
    graph.serialize(destination=OWL_PATH, format="xml")
    print(f"[Inference Engine] Completed inference. Inferred graph serialized to '{TTL_PATH}' and '{OWL_PATH}'.")


def load_ontology():
    global g
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    if os.path.exists(TTL_PATH):
        print(f"Loading existing ontology from {TTL_PATH}")
        g.parse(TTL_PATH, format="turtle")
    else:
        print("Ontology TTL file not found! Please ensure data/logistics.ttl was generated.")
        
    run_inference(g)

# Load ontology on startup
load_ontology()


# --- ROUTE: Serve the Frontend UI ---
@app.route('/')
def home():
    return render_template('index.html')


# --- API ENDPOINT: Run SPARQL Queries ---
@app.route('/api/query', methods=['POST'])
def run_query():
    data = request.json or {}
    sparql_query = data.get('query')
    if not sparql_query:
        return jsonify({"error": "No SPARQL query provided"}), 400
        
    print(f"Running SPARQL Query:\n{sparql_query}")
    try:
        res = g.query(sparql_query)
        if res.type == "SELECT":
            vars_list = [str(v) for v in res.vars]
            bindings = []
            for row in res:
                row_dict = {}
                for var in res.vars:
                    val = row[var]
                    if val is None:
                        row_dict[str(var)] = None
                    elif isinstance(val, URIRef):
                        row_dict[str(var)] = {"type": "uri", "value": str(val)}
                    elif isinstance(val, Literal):
                        row_dict[str(var)] = {
                            "type": "literal", 
                            "value": val.toPython(), 
                            "datatype": str(val.datatype) if val.datatype else None
                        }
                    else:
                        row_dict[str(var)] = {"type": "unknown", "value": str(val)}
                bindings.append(row_dict)
                
            result_json = {
                "head": {"vars": vars_list},
                "results": {"bindings": bindings}
            }
            return jsonify(result_json)
        elif res.type == "ASK":
            return jsonify({"head": {}, "boolean": res.askAnswer})
        else: # CONSTRUCT, DESCRIBE
            triples = []
            for s, p, o in res:
                triples.append({
                    "subject": str(s),
                    "predicate": str(p),
                    "object": str(o)
                })
            return jsonify({"head": {}, "results": {"triples": triples}})
    except Exception as e:
        print(f"SPARQL Error: {str(e)}")
        return jsonify({"error": str(e)}), 400


# --- API ENDPOINT: Get OWL Inference Alerts ---
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    alerts_list = []
    alert_classes = [
        LOGISTICS.Alert, 
        LOGISTICS.StorageConflictAlert, 
        LOGISTICS.TransportConflictAlert, 
        LOGISTICS.LowStockAlert, 
        LOGISTICS.CapacityAlert
    ]
    seen_alerts = set()
    for ac in alert_classes:
        for alert in g.subjects(RDF.type, ac):
            if alert in seen_alerts:
                continue
            seen_alerts.add(alert)
            msg = g.value(alert, LOGISTICS.alertMessage)
            sev = g.value(alert, LOGISTICS.alertSeverity)
            atype = g.value(alert, LOGISTICS.alertType)
            
            linked_entities = []
            for subj in g.subjects(LOGISTICS.hasAlert, alert):
                if subj != alert:
                    linked_entities.append(str(subj))
                    
            alerts_list.append({
                "id": str(alert),
                "type": str(atype) if atype else "General Warning",
                "message": str(msg) if msg else "",
                "severity": str(sev) if sev else "Info",
                "entities": linked_entities
            })
            
    # Sort alerts: Critical -> High -> Medium -> Low
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Info": 3}
    alerts_list.sort(key=lambda x: severity_order.get(x["severity"], 4))
    
    return jsonify(alerts_list)


# --- API ENDPOINT: Get Structured Entities ---
@app.route('/api/entities', methods=['GET'])
def get_entities():
    # Helper to return all items, facilities, vehicles, and officers in a clean format
    items = []
    # Since subclass reasoning was applied, all items have rdf:type StockItem
    for s in g.subjects(RDF.type, LOGISTICS.StockItem):
        # Determine subclass type
        subclass = "StandardItem"
        for t in g.objects(s, RDF.type):
            if t in [LOGISTICS.PerishableItem, LOGISTICS.HazardousItem, LOGISTICS.StandardItem]:
                subclass = t.split('#')[-1]
                
        stored_in = g.value(s, LOGISTICS.storedIn)
        assigned_to = g.value(s, LOGISTICS.assignedTo)
        managed_by = g.value(s, LOGISTICS.managedBy)
        
        items.append({
            "id": str(s),
            "localName": s.split('#')[-1],
            "type": subclass,
            "name": str(g.value(s, LOGISTICS.itemName) or ""),
            "quantity": int(g.value(s, LOGISTICS.quantity) or 0),
            "minThreshold": int(g.value(s, LOGISTICS.minThreshold) or 0),
            "requiresCooling": bool(g.value(s, LOGISTICS.requiresCooling)),
            "isHazardous": bool(g.value(s, LOGISTICS.isHazardous)),
            "storedIn": str(stored_in) if stored_in else None,
            "storedInName": str(g.value(stored_in, LOGISTICS.facilityName) or (stored_in.split('#')[-1] if stored_in else "None")),
            "assignedTo": str(assigned_to) if assigned_to else None,
            "assignedToName": str(g.value(assigned_to, LOGISTICS.vehicleName) or (assigned_to.split('#')[-1] if assigned_to else "None")),
            "managedBy": str(managed_by) if managed_by else None,
            "managedByName": str(g.value(managed_by, LOGISTICS.officerName) or (managed_by.split('#')[-1] if managed_by else "None"))
        })
        
    facilities = []
    for s in g.subjects(RDF.type, LOGISTICS.StorageFacility):
        subclass = "GeneralStorage"
        for t in g.objects(s, RDF.type):
            if t in [LOGISTICS.ColdStorage, LOGISTICS.HazardousStorage, LOGISTICS.GeneralStorage]:
                subclass = t.split('#')[-1]
        facilities.append({
            "id": str(s),
            "localName": s.split('#')[-1],
            "type": subclass,
            "name": str(g.value(s, LOGISTICS.facilityName) or ""),
            "hasCooling": bool(g.value(s, LOGISTICS.hasCooling)),
            "isHazardousApproved": bool(g.value(s, LOGISTICS.isHazardousApproved)),
            "capacity": int(g.value(s, LOGISTICS.capacity) or 0)
        })
        
    vehicles = []
    for s in g.subjects(RDF.type, LOGISTICS.TransportVehicle):
        subclass = "FlatbedTruck"
        for t in g.objects(s, RDF.type):
            if t in [LOGISTICS.RefrigeratedTruck, LOGISTICS.ChemicalTanker, LOGISTICS.FlatbedTruck]:
                subclass = t.split('#')[-1]
        vehicles.append({
            "id": str(s),
            "localName": s.split('#')[-1],
            "type": subclass,
            "name": str(g.value(s, LOGISTICS.vehicleName) or ""),
            "hasVehicleCooling": bool(g.value(s, LOGISTICS.hasVehicleCooling)),
            "hasHazardousPermit": bool(g.value(s, LOGISTICS.hasHazardousPermit))
        })
        
    officers = []
    for s in g.subjects(RDF.type, LOGISTICS.ProcurementOfficer):
        officers.append({
            "id": str(s),
            "localName": s.split('#')[-1],
            "name": str(g.value(s, LOGISTICS.officerName) or "")
        })
        
    # Return lists sorted by localName for predictable display
    items.sort(key=lambda x: x["localName"])
    facilities.sort(key=lambda x: x["localName"])
    vehicles.sort(key=lambda x: x["localName"])
    officers.sort(key=lambda x: x["localName"])
    
    # Calculate type counts for dashboard stats
    stats = {
        "items": items,
        "facilities": facilities,
        "vehicles": vehicles,
        "officers": officers,
        "tripleCount": len(g)
    }
    return jsonify(stats)


# --- API ENDPOINT: Add Entity ---
@app.route('/api/entities/add', methods=['POST'])
def add_entity():
    data = request.json or {}
    category = data.get("category")
    entity_id = data.get("id", "").strip()
    if not entity_id:
        return jsonify({"error": "ID is required"}), 400
        
    # Standardize ID
    entity_id = ''.join(c for c in entity_id if c.isalnum() or c in '_-')
    uri = URIRef(f"http://example.org/logistics#{entity_id}")
    
    # Check for duplicate
    if (uri, RDF.type, None) in g:
        return jsonify({"error": f"Entity with ID '{entity_id}' already exists."}), 400
        
    try:
        if category == "item":
            item_type = data.get("type", "StandardItem")
            g.add((uri, RDF.type, LOGISTICS[item_type]))
            g.add((uri, LOGISTICS.itemName, Literal(data.get("name"), datatype=XSD.string)))
            g.add((uri, LOGISTICS.quantity, Literal(int(data.get("quantity", 0)), datatype=XSD.integer)))
            g.add((uri, LOGISTICS.minThreshold, Literal(int(data.get("minThreshold", 0)), datatype=XSD.integer)))
            
            requires_cooling = True if item_type == "PerishableItem" else (data.get("requiresCooling") == True)
            is_hazardous = True if item_type == "HazardousItem" else (data.get("isHazardous") == True)
            g.add((uri, LOGISTICS.requiresCooling, Literal(requires_cooling, datatype=XSD.boolean)))
            g.add((uri, LOGISTICS.isHazardous, Literal(is_hazardous, datatype=XSD.boolean)))
            
            if data.get("storedIn"):
                g.add((uri, LOGISTICS.storedIn, URIRef(data.get("storedIn"))))
            if data.get("assignedTo"):
                g.add((uri, LOGISTICS.assignedTo, URIRef(data.get("assignedTo"))))
            if data.get("managedBy"):
                g.add((uri, LOGISTICS.managedBy, URIRef(data.get("managedBy"))))
                
        elif category == "facility":
            fac_type = data.get("type", "GeneralStorage")
            g.add((uri, RDF.type, LOGISTICS[fac_type]))
            g.add((uri, LOGISTICS.facilityName, Literal(data.get("name"), datatype=XSD.string)))
            g.add((uri, LOGISTICS.capacity, Literal(int(data.get("capacity", 0)), datatype=XSD.integer)))
            
            has_cooling = True if fac_type == "ColdStorage" else (data.get("hasCooling") == True)
            is_haz = True if fac_type == "HazardousStorage" else (data.get("isHazardousApproved") == True)
            g.add((uri, LOGISTICS.hasCooling, Literal(has_cooling, datatype=XSD.boolean)))
            g.add((uri, LOGISTICS.isHazardousApproved, Literal(is_haz, datatype=XSD.boolean)))
            
        elif category == "vehicle":
            veh_type = data.get("type", "FlatbedTruck")
            g.add((uri, RDF.type, LOGISTICS[veh_type]))
            g.add((uri, LOGISTICS.vehicleName, Literal(data.get("name"), datatype=XSD.string)))
            
            has_cooling = True if veh_type == "RefrigeratedTruck" else (data.get("hasVehicleCooling") == True)
            has_permit = True if veh_type == "ChemicalTanker" else (data.get("hasHazardousPermit") == True)
            g.add((uri, LOGISTICS.hasVehicleCooling, Literal(has_cooling, datatype=XSD.boolean)))
            g.add((uri, LOGISTICS.hasHazardousPermit, Literal(has_permit, datatype=XSD.boolean)))
            
        elif category == "officer":
            g.add((uri, RDF.type, LOGISTICS.ProcurementOfficer))
            g.add((uri, LOGISTICS.officerName, Literal(data.get("name"), datatype=XSD.string)))
        else:
            return jsonify({"error": "Invalid category specified."}), 400
            
        # Re-run inference and save updated graph
        run_inference(g)
        return jsonify({"success": True, "uri": str(uri)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# --- API ENDPOINT: Delete Entity ---
@app.route('/api/entities/delete', methods=['POST'])
def delete_entity():
    data = request.json or {}
    uri_str = data.get("uri")
    if not uri_str:
        return jsonify({"error": "URI is required"}), 400
        
    uri = URIRef(uri_str)
    
    # Remove all triples where entity is subject or object
    g.remove((uri, None, None))
    g.remove((None, None, uri))
    
    # Re-run inference and save updated graph
    run_inference(g)
    return jsonify({"success": True})


# --- API ENDPOINT: Update Relations (Assign storage/transport) ---
@app.route('/api/entities/update-relations', methods=['POST'])
def update_relations():
    data = request.json or {}
    item_uri_str = data.get("itemUri")
    if not item_uri_str:
        return jsonify({"error": "Item URI is required"}), 400
        
    item_uri = URIRef(item_uri_str)
    
    # Update storedIn
    if "storedInUri" in data:
        g.remove((item_uri, LOGISTICS.storedIn, None))
        stored_in_uri = data.get("storedInUri")
        if stored_in_uri and stored_in_uri != "None":
            g.add((item_uri, LOGISTICS.storedIn, URIRef(stored_in_uri)))
            
    # Update assignedTo
    if "assignedToUri" in data:
        g.remove((item_uri, LOGISTICS.assignedTo, None))
        assigned_to_uri = data.get("assignedToUri")
        if assigned_to_uri and assigned_to_uri != "None":
            g.add((item_uri, LOGISTICS.assignedTo, URIRef(assigned_to_uri)))
            
    run_inference(g)
    return jsonify({"success": True})


# --- API ENDPOINT: Fetch raw triples for Graph visualization ---
@app.route('/api/graph-data', methods=['GET'])
def get_graph_data():
    nodes = []
    edges = []
    seen_nodes = set()
    
    # Define node helper
    def add_node(uri, label, group, details=None):
        if str(uri) not in seen_nodes:
            seen_nodes.add(str(uri))
            nodes.append({
                "id": str(uri),
                "label": label,
                "group": group,
                "title": details or str(uri)
            })
            
    # Traverse graph to extract nodes and relationships
    for s, p, o in g:
        # We only want to visualize triples from our custom logistics namespace
        # or relevant rdf/rdfs relations
        if not (str(s).startswith(str(LOGISTICS)) or str(o).startswith(str(LOGISTICS))):
            continue
            
        # Ignore Alert class definitions, just visual instances
        if s in [LOGISTICS.Alert, LOGISTICS.StorageConflictAlert, LOGISTICS.TransportConflictAlert, LOGISTICS.LowStockAlert, LOGISTICS.CapacityAlert]:
            continue
            
        # Get Node Groups and Labels
        def get_group_and_label(uri):
            if uri == RDF.type:
                return "relation", "type"
                
            local_name = uri.split('#')[-1]
            
            # Check types
            types = list(g.objects(uri, RDF.type))
            if LOGISTICS.PerishableItem in types or LOGISTICS.HazardousItem in types or LOGISTICS.StandardItem in types or LOGISTICS.StockItem in types:
                name = g.value(uri, LOGISTICS.itemName)
                qty = g.value(uri, LOGISTICS.quantity)
                lbl = f"{name} ({qty})" if name and qty else local_name
                return "item", lbl
            elif LOGISTICS.ColdStorage in types or LOGISTICS.HazardousStorage in types or LOGISTICS.GeneralStorage in types or LOGISTICS.StorageFacility in types:
                name = g.value(uri, LOGISTICS.facilityName)
                lbl = str(name) if name else local_name
                return "facility", lbl
            elif LOGISTICS.RefrigeratedTruck in types or LOGISTICS.ChemicalTanker in types or LOGISTICS.FlatbedTruck in types or LOGISTICS.TransportVehicle in types:
                name = g.value(uri, LOGISTICS.vehicleName)
                lbl = str(name) if name else local_name
                return "vehicle", lbl
            elif LOGISTICS.ProcurementOfficer in types:
                name = g.value(uri, LOGISTICS.officerName)
                lbl = str(name) if name else local_name
                return "officer", lbl
            elif LOGISTICS.StorageConflictAlert in types or LOGISTICS.TransportConflictAlert in types or LOGISTICS.LowStockAlert in types or LOGISTICS.CapacityAlert in types or LOGISTICS.Alert in types:
                msg = g.value(uri, LOGISTICS.alertMessage)
                lbl = local_name.replace("Alert", "")
                return "alert", lbl
            else:
                # Class mapping
                if (uri, RDF.type, OWL.Class) in g or uri.split('#')[-1] in ["StockItem", "StorageFacility", "TransportVehicle", "ProcurementOfficer", "Alert"]:
                    return "class", local_name
                return "unknown", local_name

        s_group, s_label = get_group_and_label(s)
        
        # We skip datatype properties in visual edges to keep it clean, but add them to node info
        if isinstance(o, Literal):
            continue
            
        o_group, o_label = get_group_and_label(o)
        
        # Add nodes
        s_details = f"URI: {s}<br>Type: {s_group.capitalize()}"
        o_details = f"URI: {o}<br>Type: {o_group.capitalize()}"
        
        add_node(s, s_label, s_group, s_details)
        add_node(o, o_label, o_group, o_details)
        
        # Skip certain relations to avoid clutter
        # We only show storedIn, assignedTo, managedBy, hasAlert, subClassOf, and type
        pred_local = p.split('#')[-1]
        if p in [LOGISTICS.storedIn, LOGISTICS.assignedTo, LOGISTICS.managedBy, LOGISTICS.hasAlert, RDFS.subClassOf] or (p == RDF.type and o_group == "class"):
            edges.append({
                "from": str(s),
                "to": str(o),
                "label": pred_local,
                "arrows": "to"
            })
            
    return jsonify({"nodes": nodes, "edges": edges})


if __name__ == '__main__':
    app.run(debug=True, port=5000)