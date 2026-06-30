from vkdl.dedup import DedupIndex, file_sha256


def test_file_sha256(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    assert file_sha256(p) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_claim_new_hash_returns_none():
    idx = DedupIndex()
    assert idx.claim("h1", "001.jpg") is None


def test_claim_taken_hash_returns_first_owner():
    idx = DedupIndex()
    idx.claim("h1", "001.jpg")
    assert idx.claim("h1", "002.jpg") == "001.jpg"


def test_from_dir_indexes_existing_images(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"hello")
    (tmp_path / "notes.txt").write_bytes(b"hello")  # non-image ignored
    idx = DedupIndex.from_dir(tmp_path)
    h = file_sha256(tmp_path / "a.jpg")
    # the image content is already claimed; a second photo with same bytes is a dup
    assert idx.claim(h, "b.jpg") == "a.jpg"
