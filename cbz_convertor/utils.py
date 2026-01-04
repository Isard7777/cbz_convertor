"""
Utility functions for CBZ Convertor.
"""

from typing import Any


from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

def  generate_comic_info_xml(metadata: dict[str, Any]) -> str:
    """
    Generate ComicInfo.xml content from metadata dictionary.

    Args:
        metadata: Dictionary containing comic metadata
    Returns:
        str: ComicInfo.xml content
    """

    root = Element("ComicInfo")

    xsd_fields = {
        "Title", "Series", "Volume", "Summary", "Notes", "Year", "Writer", "Penciller", "Publisher", "Genre",
        "PageCount", "LanguageISO"
    }

    for field in xsd_fields:
        if field in metadata and metadata[field] is not None:
            elem = SubElement(root, field)
            if type(metadata[field]) == list:
                elem.text = ", ".join(metadata[field])
            else:
                elem.text = str(metadata[field])

    xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="  ")

    return "\n".join(line for line in xml_str.split("\n")[1:] if line.strip())



def get_nested_value(data: dict, *keys: str, default: Any = None) -> Any:
    """
    Safely extract a value from nested dictionaries.

    Args:
        data: The dictionary to extract from
        *keys: Variable number of keys for nested access
        default: Default value if key path doesn't exist or value is falsy

    Returns:
        The value at the nested key path, or default if not found or falsy

    Examples:
        >>> data = {"series": {"title": "My Series", "language": "en"}}
        >>> get_nested_value(data, "series", "title")
        'My Series'
        >>> get_nested_value(data, "series", "author", default="Unknown")
        'Unknown'
        >>> get_nested_value(data, "series", "title", default="Fallback")
        'My Series'
    """
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]

    # Return default if value is falsy (None, empty string, etc.)
    return current if current else default

