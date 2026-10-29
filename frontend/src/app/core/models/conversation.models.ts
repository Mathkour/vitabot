export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ConversationSummary {
  conversation_id: string;
  started_at: string;
  messages: ConversationMessage[];
}

export interface UserConversationsResponse {
  user: {
    username: string;
    email: string;
  };
  conversations: ConversationSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface MyConversationsResponse {
  conversations: ConversationSummary[];
}
