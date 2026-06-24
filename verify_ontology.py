import os
import sys
from rdflib import Graph, RDF, URIRef, Namespace
from rdflib.namespace import RDFS

# Define namespaces
LOGISTICS = Namespace("http://example.org/logistics#")

def run_tests():
    print("==================================================")
    print("      IMKS ONTOLOGY INTEGRITY VERIFICATION        ")
    print("==================================================")
    
    # 1. Test app.py load & import
    try:
        import app
        print("[PASS] app.py successfully imported.")
    except Exception as e:
        print(f"[FAIL] Failed to import app.py: {e}")
        sys.exit(1)
        
    # Check if files exist
    if not os.path.exists(app.TTL_PATH):
        print(f"[FAIL] Ontology Turtle file missing at {app.TTL_PATH}")
        sys.exit(1)
    if not os.path.exists(app.OWL_PATH):
        print(f"[FAIL] Ontology RDF/XML file missing at {app.OWL_PATH}")
        sys.exit(1)
    print("[PASS] Both logistics.ttl and logistics.owl exist.")

    # 2. Test graph instances loading
    g = app.g
    triple_count = len(g)
    print(f"[INFO] Loaded graph has {triple_count} triples.")
    if triple_count < 50:
        print("[FAIL] Graph too small. Check if seed data loaded correctly.")
        sys.exit(1)
    print("[PASS] Triple store successfully populated with seed data.")

    # 3. Test RDFS subclass transitive inference
    # Fresh Milk is PerishableItem, which is subclass of StockItem.
    # Check if (Item_FreshMilk, type, StockItem) is asserted in graph.
    fresh_milk = LOGISTICS.Item_FreshMilk
    if (fresh_milk, RDF.type, LOGISTICS.StockItem) in g:
        print("[PASS] Subclass transitive reasoning working (FreshMilk is inferred as StockItem).")
    else:
        print("[FAIL] Subclass reasoning failed. FreshMilk is NOT inferred as StockItem.")
        sys.exit(1)

    # 4. Test safety rule inferences (cooling & hazardous conflicts)
    # Frozen Fish is perishable but stored in Warehouse A (lacks cooling)
    frozen_fish = LOGISTICS.Item_FrozenFish
    alerts_on_fish = list(g.objects(frozen_fish, LOGISTICS.hasAlert))
    if alerts_on_fish:
        print(f"[PASS] Cooling safety rule triggered on FrozenFish. Alerts: {alerts_on_fish}")
    else:
        print("[FAIL] Safety rule failed. No alert generated for FrozenFish stored without cooling.")
        sys.exit(1)

    # Sulfuric Acid is hazardous but stored in Warehouse A (non-approved)
    sulfuric_acid = LOGISTICS.Item_SulfuricAcid
    alerts_on_acid = list(g.objects(sulfuric_acid, LOGISTICS.hasAlert))
    if alerts_on_acid:
        print(f"[PASS] Hazard safety rule triggered on SulfuricAcid. Alerts: {alerts_on_acid}")
    else:
        print("[FAIL] Safety rule failed. No alert generated for SulfuricAcid stored in non-approved facility.")
        sys.exit(1)

    # 5. Test capacity calculations and warnings
    # Add a large item to ColdHub_1 to exceed capacity (500 limit)
    print("[INFO] Testing capacity overflow rule...")
    temp_item = LOGISTICS.Item_Overload
    g.add((temp_item, RDF.type, LOGISTICS.StandardItem))
    g.add((temp_item, LOGISTICS.itemName, Literal("Overload Cargo", datatype=app.XSD.string)))
    g.add((temp_item, LOGISTICS.quantity, Literal(600, datatype=app.XSD.integer)))
    g.add((temp_item, LOGISTICS.storedIn, LOGISTICS.ColdHub_1))
    
    # Run inference to evaluate
    app.run_inference(g)
    
    alerts_on_hub = list(g.objects(LOGISTICS.ColdHub_1, LOGISTICS.hasAlert))
    capacity_alerts = [a for a in alerts_on_hub if (a, RDF.type, LOGISTICS.CapacityAlert) in g]
    if capacity_alerts:
        print(f"[PASS] Capacity validation triggered alerts on ColdHub_1: {capacity_alerts}")
    else:
        print("[FAIL] Capacity constraint failed to trigger alert on overload.")
        sys.exit(1)
        
    # Clean up overload test
    g.remove((temp_item, None, None))
    app.run_inference(g)

    # 6. Test SPARQL SELECT Query Execution
    test_query = """
    PREFIX logistics: <http://example.org/logistics#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?name ?qty
    WHERE {
      ?item rdf:type logistics:StockItem .
      ?item logistics:itemName ?name .
      ?item logistics:quantity ?qty .
    }
    """
    try:
        qres = g.query(test_query)
        print(f"[PASS] SPARQL SELECT query executed successfully. Returned {len(qres)} rows.")
        for row in qres:
            print(f"       Item: {row.name} | Qty: {row.qty}")
    except Exception as e:
        print(f"[FAIL] SPARQL query execution failed: {e}")
        sys.exit(1)

    print("\n==================================================")
    print("    ALL TESTS PASSED SUCCESSFULLY! SYSTEM STABLE. ")
    print("==================================================")

if __name__ == '__main__':
    # Write a quick literal helper from rdflib
    from rdflib import Literal
    run_tests()
