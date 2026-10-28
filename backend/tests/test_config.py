import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("configured_url", "expected_url"),
    [
        ("https://project.supabase.co", "https://project.supabase.co"),
        ("https://project.supabase.co/", "https://project.supabase.co"),
        ("https://project.supabase.co/rest/v1/", "https://project.supabase.co"),
        ("https://project.supabase.co/auth/v1", "https://project.supabase.co"),
    ],
)
def test_supabase_url_normalizes_api_endpoint_suffixes(
    configured_url: str,
    expected_url: str,
) -> None:
    settings = Settings(supabase_url=configured_url)

    assert settings.supabase_url == expected_url

