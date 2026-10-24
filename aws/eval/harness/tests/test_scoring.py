from harness.dataset import Checkbox, Edge
from harness.scoring import (
    cer,
    checkbox_accuracy,
    edge_scores,
    hallucination_rate,
    normalize,
    word_scores,
)


def test_normalize_strips_markup_and_annotations():
    assert normalize("# RAG revision:\n- [x] Test *code*\n- Lightsail Box (boundary box)") == \
        "rag revision test code lightsail box"


def test_normalize_arrows():
    assert normalize("A → B") == normalize("A -> B") == normalize("A => B") == "a b"


def test_normalize_drops_untitled_heading():
    assert normalize("# Crawlers architecture (untitled)\n- Crawler 1") == "crawler 1"


def test_normalize_drops_scaffolding_keeps_label():
    assert normalize('## Diagram\nEdges:\n- A → B, labelled "API key"') == "api key"


def test_normalize_counts_node_names_once():
    # Node names are written once on the board; edge lines only add their labels.
    md = '## Diagram\n- Chunk\n- Vector store\nEdges:\n- Chunk → Vector store, labelled "embed"\n- Vector store → Chunk\n\n## TODO\n- a → b'
    assert normalize(md) == "chunk vector store embed todo a b"


def test_normalize_keeps_lambda():
    assert normalize("Pre-Sign URL λ") == "pre sign url λ"


def test_word_scores():
    p, r, f = word_scores("store data in a vectorized manner", "stone data in a vectorized manner")
    assert (round(p, 3), round(r, 3)) == (0.833, 0.833)


def test_word_scores_empty_hyp():
    assert word_scores("a b", "") == (0.0, 0.0, 0.0)


def test_cer():
    assert cer("store", "stone") == 0.2


def test_hallucination_rate():
    assert hallucination_rate("a b c", "a b zzz zzz") == 0.5
    assert hallucination_rate("a b", "") == 0.0


def test_edge_scores_fuzzy_and_label():
    ref = [Edge("ESP32 CAM", "API Gateway", "API key"), Edge("API Gateway", "Pre-Sign URL λ", None)]
    hyp = [Edge("ESP32 cam", "API Gatway", "API key"), Edge("API Gateway", "Lambda", None)]
    assert edge_scores(ref, hyp) == (0.5, 0.5)    # "lambda" vs "pre sign url λ" is far below 80


def test_edge_label_must_match_when_ref_has_one():
    assert edge_scores([Edge("A box", "B box", "copy complete")],
                       [Edge("A box", "B box", "upload")]) == (0.0, 0.0)


def test_edge_scores_no_ref_edges():
    assert edge_scores([], [Edge("a", "b", None)]) == (None, None)


def test_checkbox_accuracy():
    ref = [Checkbox("Test terraform code", True), Checkbox("Finalize IR sensor", False)]
    hyp = [Checkbox("Test teraform code", True), Checkbox("Finalize IR sensor", True)]
    assert checkbox_accuracy(ref, hyp) == 0.5
    assert checkbox_accuracy([], hyp) is None
