# TSW6223 SEMANTIC WEB TECHNOLOGY PROJECT REPORT
## TERM 2610

**Title:** Inventory Management Knowledge System (IMKS)  
**Group ID:** Group XX *(Please replace with your registered Group ID)*  
**Selected Topics:**  
1. **Category 2:** Resource Description Framework (RDF), RDF with Schema (RDFS), and SPARQL Protocol and RDF Query Language  
2. **Category 3:** Web Ontology Language (OWL) and/or inference  

---

### Members & Contributions

| Name / Student ID | List contribution(s) in the project | State which part of the write-up in the report |
| :--- | :--- | :--- |
| **Patrick Lim Wei Jie** / 21110000 | Designed RDFS/OWL ontology schema (`logistics.ttl`), built Flask REST APIs, and implemented SPARQL query bindings. | Section 1 (Introduction), Section 3 (Solution Development - Ontology Design), Section 7 (References). |
| **Student 2 Name** / ID | Implemented the Python-based custom OWL inference rules engine, capacity constraints, and alert assertions. | Section 2 (Problem Statement & Objectives), Section 3 (Solution Development - Inference Engine). |
| **Student 3 Name** / ID | Developed the frontend interface (`index.html`), integrated TailwindCSS, Vis.js graph network explorer, and CRUD panels. | Section 4 (Evaluation - UI Screens), Section 5 (Future Improvements). |
| **Student 4 Name** / ID | Conducted verification testing, drafted sample SPARQL queries, and compiled final documentation. | Section 4 (Evaluation - Testing & Queries), Section 6 (Conclusion). |

---
\pagebreak

# Project Report

## 1. Introduction
Semantic Web Technology (SWT) represents an evolution of the World Wide Web aimed at making web data machine-readable, structured, and semantically interconnected. Traditional data storage systems, such as relational databases, represent data in isolated tables and rely on rigid schemas that obscure conceptual relationships. SWT addresses this limitation by using standards like the **Resource Description Framework (RDF)**, **RDF Schema (RDFS)**, and the **Web Ontology Language (OWL)** to express information as logical graphs of subjects, predicates, and objects (triples).

In the context of enterprise logistics, inventory systems are traditionally fragmented. Data regarding items, warehouses, transport vehicles, and staff reside in separate silos, making it difficult to detect cross-domain conflicts (such as safety rule violations or temperature mismatches). 

This project develops the **Inventory Management Knowledge System (IMKS)**. IMKS represents inventory data semantically, allowing:
- Hierarchical class modeling via RDFS and OWL.
- Semantic querying via **SPARQL**.
- Rule-based compliance checking and automated warning generation via an inference engine.

---

## 2. Problem Statement and Objectives

### 2.1 Problem Statement
Industrial warehouses handle diverse categories of goods, including perishable items (which require continuous refrigeration) and hazardous goods (which require specialised environmental permits). Traditional inventory tracking software suffers from three main limitations:
1. **Lack of Semantic Context**: Relational databases store assignments (e.g., `item_102 stored in warehouse_A`) without representing the underlying constraints of those entities (e.g., that `item_102` is perishable and `warehouse_A` lacks cooling).
2. **Manual and Error-Prone Compliance**: Safety regulations, storage constraints, and vehicle assignment rules must be written in custom application code, making them difficult to audit, scale, or adapt as regulations change.
3. **No Automatic Inference**: Relational databases cannot automatically infer class inheritance (e.g., that a `RefrigeratedTruck` is transitively a `TransportVehicle`) or generate semantic alerts without complex join queries.

### 2.2 Project Objectives
1. **Develop a Semantic Inventory Model**: Design a RDFS/OWL ontology that models inventory items, warehouses, transport fleets, and staff.
2. **Implement Automated Semantic Inference**: Build a reasoning engine to execute logical rules, identify conflicts (e.g., temperature mismatches, hazardous goods storage, capacity limits), and assert alerts into the RDF triple store.
3. **Provide SPARQL Query Capabilities**: Enable structured, complex querying of the active and inferred triple store.
4. **Deliver a Visual Graph Explorer**: Create an interactive Web interface to display the real-time node-link diagram of the knowledge base.

---

## 3. Solution Development

### 3.1 Ontology Architecture and Design
The ontology is defined in Turtle (`.ttl`) format and serialized into RDF/XML (`.owl`) for standard tool compatibility. 

#### Class Hierarchy
- `logistics:Entity` (Root Class)
  - `logistics:StockItem`
    - `logistics:PerishableItem`
    - `logistics:HazardousItem`
    - `logistics:StandardItem`
  - `logistics:StorageFacility`
    - `logistics:ColdStorage`
    - `logistics:HazardousStorage`
    - `logistics:GeneralStorage`
  - `logistics:TransportVehicle`
    - `logistics:RefrigeratedTruck`
    - `logistics:ChemicalTanker`
    - `logistics:FlatbedTruck`
  - `logistics:ProcurementOfficer`
  - `logistics:Alert`
    - `logistics:StorageConflictAlert`
    - `logistics:TransportConflictAlert`
    - `logistics:LowStockAlert`
    - `logistics:CapacityAlert`

#### Core Object Properties
- `logistics:storedIn` (Domain: `logistics:StockItem`, Range: `logistics:StorageFacility`)
- `logistics:assignedTo` (Domain: `logistics:StockItem`, Range: `logistics:TransportVehicle`)
- `logistics:managedBy` (Domain: `logistics:StockItem`, Range: `logistics:ProcurementOfficer`)
- `logistics:hasAlert` (Domain: `logistics:Entity`, Range: `logistics:Alert`)

#### Core Datatype Properties
- `logistics:quantity` (Range: `xsd:integer`)
- `logistics:minThreshold` (Range: `xsd:integer`)
- `logistics:requiresCooling` (Range: `xsd:boolean`)
- `logistics:isHazardous` (Range: `xsd:boolean`)
- `logistics:hasCooling` (Range: `xsd:boolean`)
- `logistics:isHazardousApproved` (Range: `xsd:boolean`)
- `logistics:capacity` (Range: `xsd:integer`)
- `logistics:hasVehicleCooling` (Range: `xsd:boolean`)
- `logistics:hasHazardousPermit` (Range: `xsd:boolean`)

---

### 3.2 Python-Based Inference Engine
Because Java-based OWL reasoners (such as HermiT or Pellet) are not pre-installed in the deployment environment, we implemented a custom rule-based inference engine in the Flask backend using `rdflib`. 

#### Subclass Reasoning Loop
This loop computes the transitive closure of subclasses. If class `A` is a subclass of `B`, and instance `x` has type `A`, the reasoner asserts `(x, rdf:type, B)`.
```python
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
```

#### Rule Assertions
The reasoner evaluates five compliance rules and asserts `logistics:Alert` nodes for any violations:
1. **Cooling Rule**: `StockItem(x) ∧ requiresCooling(x, true) ∧ storedIn(x, y) ∧ hasCooling(y, false) → StorageConflictAlert(alert)`
2. **Hazard Rule**: `StockItem(x) ∧ isHazardous(x, true) ∧ storedIn(x, y) ∧ isHazardousApproved(y, false) → StorageConflictAlert(alert)`
3. **Low Stock Rule**: `StockItem(x) ∧ quantity(x, q) ∧ minThreshold(x, t) ∧ (q < t) → LowStockAlert(alert)`
4. **Capacity Rule**: `StorageFacility(y) ∧ capacity(y, c) ∧ (Sum(quantity(x)) > c) → CapacityAlert(alert)`
5. **Transport Cooling Rule**: `StockItem(x) ∧ requiresCooling(x, true) ∧ assignedTo(x, v) ∧ hasVehicleCooling(v, false) → TransportConflictAlert(alert)`
6. **Transport Hazard Rule**: `StockItem(x) ∧ isHazardous(x, true) ∧ assignedTo(x, v) ∧ hasHazardousPermit(v, false) → TransportConflictAlert(alert)`

---

## 4. Evaluation and Testing

### 4.1 Evaluation of OWL Inference Alerts
To test the inference rules, conflict instances were seeded in the ontology:
- **`logistics:Item_FrozenFish`**: Marked as a `PerishableItem` (`requiresCooling = true`) but stored in `logistics:Warehouse_A` (`hasCooling = false`). The reasoner generated a `StorageCoolingAlert` alert.
- **`logistics:Item_SulfuricAcid`**: Marked as a `HazardousItem` (`isHazardous = true`) but stored in `logistics:Warehouse_A` (`isHazardousApproved = false`). The reasoner generated a `StorageHazardAlert` alert.
- **`logistics:Item_LiquidNitrogen`**: Stock count set to `80`, below its `minThreshold` of `100`. The reasoner asserted a `LowStockAlert` warning.

---

### 4.2 SPARQL Query Test Cases
The system provides four sample SPARQL queries to extract information from the triple store.

#### Test Query 1: Find Perishable Storage Conflicts
```sparql
PREFIX logistics: <http://example.org/logistics#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?item ?itemName ?facility ?facilityName
WHERE {
  ?item rdf:type logistics:PerishableItem .
  ?item logistics:itemName ?itemName .
  ?item logistics:storedIn ?facility .
  ?facility logistics:facilityName ?facilityName .
  ?facility logistics:hasCooling "false"^^xsd:boolean .
}
```
*Expected Output:*
- `?item`: `logistics:Item_FrozenFish`
- `?itemName`: `"Frozen Salmon Filets"`
- `?facility`: `logistics:Warehouse_A`
- `?facilityName`: `"Main Warehouse A"`

#### Test Query 2: Aggregate Capacity Space Check
This query showcases complex SPARQL features (`SUM`, `GROUP BY`, and mathematical expressions) to calculate remaining capacity:
```sparql
PREFIX logistics: <http://example.org/logistics#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?facility ?facName ?capacity (SUM(?qty) AS ?totalStored) (?capacity - SUM(?qty) AS ?remainingSpace)
WHERE {
  ?facility rdf:type logistics:StorageFacility .
  ?facility logistics:facilityName ?facName .
  ?facility logistics:capacity ?capacity .
  OPTIONAL {
    ?item logistics:storedIn ?facility .
    ?item logistics:quantity ?qty .
  }
}
GROUP BY ?facility ?facName ?capacity
```

---

### 4.3 Web UI Evaluation
The web application provides four primary panels to interact with the knowledge base:
1. **System Dashboard**:
   - Displays real-time metrics (RDF triple count, total stock items, warehouses, active alerts).
   - Renders a list of active alerts color-coded by severity (Critical, High, Medium, Info).
   - Provides **"Reassign"** shortcuts for each conflict, allowing users to reallocate items to compatible storage or vehicles.
2. **SPARQL Console**:
   - Includes a text editor loaded with syntax themes and query presets.
   - Executes queries against the live graph, displaying results in a dynamic HTML table.
   - Includes a raw JSON inspector to view standard SPARQL JSON responses.
3. **RDF Graph View**:
   - Uses the **Vis.js** library to display the active RDF graph.
   - Nodes are color-coded by semantic class (StockItem, StorageFacility, TransportVehicle, Officer, Alert, Class).
   - Edges represent active predicates (`storedIn`, `assignedTo`, `managedBy`, `hasAlert`).
   - Clicking a node displays its URI and properties in the Inspector sidebar.
4. **Entity Manager**:
   - Provides a CRUD interface to view, add, and delete entities.
   - Forms dynamically render input fields based on the selected class (e.g., showing refrigeration checkboxes only for vehicles or warehouses).

---

## 5. Future Improvements
1. **Integrate SWRL and SHACL**: Use SHACL (Shapes Constraint Language) to validate constraints before data is written to the graph, and support direct SWRL rules for complex conditional logic.
2. **Connect Live IoT Sensors**: Link the ontology to live IoT temperature and GPS sensors, enabling the reasoner to generate alerts if a vehicle's temperature rises above a perishable item's threshold in transit.
3. **Decentralized Federation (SPARQL Federated Queries)**: Implement SPARQL `SERVICE` blocks to link IMKS to external knowledge bases, such as safety guidelines on WikiData.

---

## 6. Conclusion
The Inventory Management Knowledge System (IMKS) demonstrates the utility of Semantic Web Technologies (SWT) for enterprise operations. By modeling inventory concepts in a unified RDF/OWL ontology, we resolved data fragmentation and enabled automated compliance checks. 

The custom Python inference engine successfully simulates OWL reasoners by resolving class hierarchies and asserting compliance alerts directly into the graph. Finally, the interactive Web UI and SPARQL console provide a user-friendly interface for logistics staff to inspect and manage the knowledge graph.

---

## 7. References (APA Style)
- Bizer, C., Heath, T., & Berners-Lee, T. (2009). Linked data - the story so far. *International Journal on Semantic Web and Information Systems*, 5(3), 1-22.
- Brickley, D., & Guha, R. V. (2014). *RDF Schema 1.1*. W3C Recommendation. Retrieved from https://www.w3.org/TR/rdf-schema/
- Harris, S., Seaborne, A., & Prud'hommeaux, E. (2013). *SPARQL 1.1 Query Language*. W3C Recommendation. Retrieved from https://www.w3.org/TR/sparql11-query/
- Hitzler, P., Krötzsch, M., Parsia, B., Patel-Schneider, P. F., & Rudolph, S. (2012). *OWL 2 Web Ontology Language Primer (Second Edition)*. W3C Recommendation. Retrieved from https://www.w3.org/TR/owl2-primer/
- Lamy, J. B. (2017). Owlready2: An object-oriented python module for ontology-oriented programming, with or without reasoner. *Artificial Intelligence in Medicine*, 80, 11-14.
