from supabase import create_client


SUPABASE_URL = "https://fhcdgungwwtleuioryrp.supabase.co"

SUPABASE_KEY = "sb_publishable_1DBt3sgPyZijNHN9vR9RKg_Y40VjqR7"


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)