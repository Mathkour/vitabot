export interface VideoItem {
  id: string;
  display_name?: string | null;
  display_name_ar?: string | null;
  description: string;
  description_ar?: string | null;
  url: string;
  category_id: string;
  category_name: string;
}
