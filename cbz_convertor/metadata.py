from dataclasses import dataclass, fields
from typing import Optional

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


@dataclass
class Metadata:
    title: Optional[str] = None
    series: Optional[str] = None
    number: Optional[str] = None
    volume: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    writers: Optional[list[str]] = None
    pencilers: Optional[list[str]] = None
    inkers: Optional[list[str]] = None
    colorists: Optional[list[str]] = None
    letterers: Optional[list[str]] = None
    cover_artists: Optional[list[str]] = None
    editors: Optional[list[str]] = None
    translators: Optional[list[str]] = None
    publishers: Optional[list[str]] = None
    genres: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    page_count: Optional[int] = None
    language: Optional[str] = None
    identifier: Optional[str] = None



    def to_comicinfo_xml(self) -> str:
        """
            Function to generate ComicInfo.xml content from metadata dictionary.
            :return: an XML string
        """

        field_mapping = {
            "title": "Title",
            "series": "Series",
            "number": "Number",
            "volume": "Volume",
            "summary": "Summary",
            "year": "Year",
            "month": "Month",
            "day": "Day",
            "writers": "Writer",
            "pencilers": "Penciller",
            "inkers": "Inker",
            "colorists": "Colorist",
            "letterers": "Letterer",
            "cover_artists": "CoverArtist",
            "editors": "Editor",
            "publishers": "Publisher",
            "genres": "Genre",
            "tags": "Tags",
            "page_count": "PageCount",
            "language": "LanguageISO",
        }
        root = Element("ComicInfo")

        notes = None

        if self.notes:
            notes = self.notes

        if self.translators:
            notes = (f"{notes}\n"
                     f"Translated by {','.join(self.translators)}.") \
                if notes else f"Translated by {','.join(self.translators)}."


        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None and field.name in field_mapping:
                tag_name = field_mapping[field.name]

                if isinstance(value, list):
                    text = ", ".join(value)
                else:
                    text = str(value)

                elem = SubElement(root, tag_name)
                elem.text = text

        if notes:
            elem = SubElement(root, "Notes")
            elem.text = notes

        xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="   ")

        return "\n".join(line for line in xml_str.split("\n")[1:] if line.strip())
