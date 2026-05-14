import os
import uuid
import urllib.request


def upload_to_catbox(file_path: str) -> str:
    """Upload un fichier sur catbox.moe et retourne l'URL publique.

    Lève une exception en cas d'échec (timeout, erreur HTTP, réponse inattendue).
    """
    filename = os.path.basename(file_path)
    boundary = f"----CatboxBoundary{uuid.uuid4().hex}"

    with open(file_path, "rb") as fh:
        file_data = fh.read()

    ext = os.path.splitext(filename)[1].lower()
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
    }.get(ext, "application/octet-stream")

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
        f"fileupload\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload";'
        f' filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "https://catbox.moe/user/api.php",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "AudiobookManager/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = resp.read().decode("utf-8").strip()

    if not result.startswith("https://"):
        raise RuntimeError(f"Réponse inattendue de catbox.moe : {result!r}")
    return result
