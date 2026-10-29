export type SupportTicketStatus = 'pending' | 'resolved';
export type SupportTicketMessageSender = 'user' | 'admin';

export interface SupportTicket {
  id: string;
  question: string;
  status: SupportTicketStatus;
  created_at: string;
  resolved_at?: string | null;
  user_last_read_at?: string | null;
}

export interface AdminSupportTicket {
  id: string;
  question: string;
  status: SupportTicketStatus;
  created_at: string;
  resolved_at: string | null;
  user_id: string;
  username: string | null;
  email: string;
  company_id: string | null;
}

export interface SupportTicketMessage {
  id: string;
  sender: SupportTicketMessageSender;
  content: string;
  created_at: string;
}

export interface UnseenSupportTicket {
  id: string;
  question: string;
  status: SupportTicketStatus;
  latest_admin_message: string | null;
  latest_admin_message_at: string | null;
}
