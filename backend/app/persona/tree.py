"""Product-rooted Cluster → Persona → Context hierarchy for stage eight."""
from app.persona.package import Package


def build_tree(package: Package, product: str) -> dict:
    """Use source doc_count for Persona/Context sizes; sum Personas above them.

    Cluster names are absent from the Evidence Package contract, so their IDs
    serve as labels. Preserve confirmed Persona/Context names and package order.
    """
    root = {'id': 'product', 'name': product, 'type': 'product', 'size': 0, 'children': []}
    clusters = {}
    for block in package.personas:
        persona = block.persona_evidence
        cid = persona.cluster_id
        if cid not in clusters:
            clusters[cid] = {'id': cid, 'name': cid, 'type': 'cluster', 'size': 0, 'children': []}
            root['children'].append(clusters[cid])
        node = {'id': persona.persona_id, 'name': persona.persona_name, 'type': 'persona',
                'size': persona.metrics.doc_count, 'children': [
                    {'id': c.context_id, 'name': c.context_name, 'type': 'context',
                     'size': c.metrics.doc_count, 'children': []}
                    for c in block.context_evidence
                ]}
        clusters[cid]['children'].append(node)
        clusters[cid]['size'] += node['size']
        root['size'] += node['size']
    return root
