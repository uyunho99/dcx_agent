import json

from app.persona.package import Package
from app.persona.tree import build_tree
from tests.fixtures.evidence_package import make_package


def test_tree_three_layers_and_doc_count_sizes():
    raw = make_package()
    # Interleaved clusters must group without losing Persona order or identity.
    for index, block in enumerate(raw['personas']):
        block['persona_evidence']['cluster_id'] = f'CL{index % 2}'
        block['persona_evidence']['metrics']['doc_count'] = 100 + index
        for offset, context in enumerate(block['context_evidence']):
            context['metrics']['doc_count'] = index * 10 + offset
    package = Package.model_validate(raw)
    before = package.model_dump()
    tree = build_tree(package, 'LG 에어컨')
    assert tree['type'] == 'product'
    assert tree['name'] == 'LG 에어컨'
    assert tree['size'] == 406
    assert [c['id'] for c in tree['children']] == ['CL0', 'CL1']
    for cluster in tree['children']:
        assert cluster['type'] == 'cluster'
        blocks = [b for b in package.personas if b.persona_evidence.cluster_id == cluster['id']]
        assert cluster['size'] == sum(b.persona_evidence.metrics.doc_count for b in blocks)
        assert [p['id'] for p in cluster['children']] == [b.persona_evidence.persona_id for b in blocks]
        for persona, block in zip(cluster['children'], blocks):
            assert persona['type'] == 'persona'
            assert persona['name'] == block.persona_evidence.persona_name
            assert persona['size'] == block.persona_evidence.metrics.doc_count
            assert [c['id'] for c in persona['children']] == [c.context_id for c in block.context_evidence]
            for leaf, context in zip(persona['children'], block.context_evidence):
                assert leaf == {'id': context.context_id, 'name': context.context_name,
                                'type': 'context', 'size': context.metrics.doc_count, 'children': []}
    assert package.model_dump() == before
    json.dumps(tree)


def test_empty_tree():
    raw = make_package()
    raw['personas'] = []
    tree = build_tree(Package.model_validate(raw), 'Product')
    assert tree['name'] == 'Product'
    assert tree['size'] == 0
    assert tree['children'] == []


def test_persona_without_contexts_is_preserved():
    raw = make_package(personas=1, contexts=(1,))
    raw['personas'][0]['context_evidence'] = []
    tree = build_tree(Package.model_validate(raw), 'Product')
    persona = tree['children'][0]['children'][0]
    assert persona['id'] == 'CL0-P0'
    assert persona['size'] == 8
    assert persona['children'] == []
