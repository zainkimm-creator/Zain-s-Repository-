# Uploaded Data

Use this folder for data files uploaded through the API or copied into the project manually.

The backend upload route is:

```text
POST /upload
```

The request field name must be `file`. Uploaded files are saved here using the filename basename only.
