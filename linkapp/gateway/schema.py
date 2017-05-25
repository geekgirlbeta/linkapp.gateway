link_schema = {
    "type": "object",
    "properties": {
        "page_title": { "type": "string", "minLength":1 },
        "desc_text": { "type": "string", "minLength":1 },
        "url_address": { "type": "string", "minLength":1 },
        "author": { "type": "string", "minLength":1 }
    }
}

link_add_schema = link_schema.copy()
link_add_schema["required"] = ["page_title", "desc_text", "url_address", "author"]