from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

# Addresses that belong to the server's own endpoints: a mistake there must stay a real 404.
_SERVER_PREFIXES = ("api/", "telegram/", "instagram/", "health")


class SinglePageStaticFiles(StaticFiles):
    """Serves the built site, and shows the app itself (instead of a bare "Not Found") when someone opens an
    address that isn't a real file, such as a mistyped link like /ref=linkedin. Missing files with an
    extension (a broken .js or .png) and mistyped API addresses are still plain 404s."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            clean = path.replace("\\", "/")  # Windows hands the path over with backslashes
            last_part = clean.rsplit("/", 1)[-1]
            looks_like_a_page = "." not in last_part and not clean.startswith(_SERVER_PREFIXES)
            if exc.status_code == 404 and looks_like_a_page:
                return await super().get_response("index.html", scope)
            raise
