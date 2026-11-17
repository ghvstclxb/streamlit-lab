import hashlib

def file_fingerprint(name, data):
    return hashlib.sha256(name.encode('utf-8') + b'\0' + data).hexdigest()

def text_deltas(events):
    for event in events:
        if event.type == 'response.output_text.delta':
            yield event.delta
        elif event.type == 'error':
            raise RuntimeError(str(event))
