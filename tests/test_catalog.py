from anysection import Section, SectionCatalog, SectionProperty


def sample_section():
    section = Section(
        name="IPE 300",
        series="IPE",
        standard="EN 10365",
        manufacturer="Example",
        source="test",
        source_url="https://example.test/ipe300",
    )
    section.add_property(
        SectionProperty(
            key="A",
            symbol="A",
            value=53.8,
            unit="cm^2",
            group="Sectional Area",
            source="test",
        )
    )
    return section


def test_catalog_roundtrip(tmp_path):
    catalog = SectionCatalog(tmp_path / "sections.sqlite")
    original = sample_section()
    catalog.upsert(original)

    assert catalog.count_sections() == 1
    assert catalog.count_properties() == 1

    loaded = catalog.get(original.identifier)
    assert loaded is not None
    assert loaded.name == "IPE 300"
    assert loaded.value("A") == 53.8

    found = catalog.find(series="ipe")
    assert len(found) == 1
    assert found[0].identifier == original.identifier


def test_scrape_status(tmp_path):
    catalog = SectionCatalog(tmp_path / "sections.sqlite")
    url = "https://example.test/series"
    assert catalog.scrape_status(url) is None
    catalog.record_scrape(url, status="ok", section_count=3)
    assert catalog.scrape_status(url) == "ok"
