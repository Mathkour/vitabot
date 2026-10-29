import { LinkType } from './category.models';

export interface MediaUploadResponse {
  id: string;
  filename: string;
  display_name?: string | null;
  media_type: string;
  description: string;
}

export interface MediaLinkResponse {
  id: string;
  description: string;
  url: string;
  link_type: LinkType;
  display_name?: string | null;
}
