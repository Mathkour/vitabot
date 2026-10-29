import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { ChatService } from '../../core/services/chat.service';
import { WidgetConfig, WidgetSessionService } from '../../core/services/widget-session.service';
import { WidgetChat } from './widget-chat';

describe('WidgetChat', () => {
  const config: WidgetConfig = {
    tenant: 'creditplus',
    bot_name: 'credit plus Assistant',
    tenant_name: 'credit plus',
    icon_color: '#2563EB',
    primary_color: '#16244C',
    logo_path: null,
    suggested_questions: ['What are your hours?', 'How do I reset my password?'],
  };

  let askSpy: ReturnType<typeof vi.fn>;

  function createComponent(): WidgetChat {
    window.location.hash = '#tenant=creditplus&token=partner-jwt';

    askSpy = vi.fn().mockReturnValue(
      of({
        conversation_id: 'c1',
        message_id: 'm1',
        answer: 'Here is the answer.',
        sources: [],
        media: null,
      }),
    );

    TestBed.configureTestingModule({
      imports: [WidgetChat],
      providers: [
        provideZonelessChangeDetection(),
        {
          provide: WidgetSessionService,
          useValue: {
            loadConfig: () => of(config),
            verify: () => of(undefined),
            clear: () => {},
            tenant: () => 'creditplus',
            username: () => null,
          },
        },
        { provide: ChatService, useValue: { ask: askSpy } },
      ],
    });

    const fixture = TestBed.createComponent(WidgetChat);
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  afterEach(() => {
    window.location.hash = '';
  });

  it('reaches the ready phase with the config-supplied suggested questions, and starts with the empty state showing', () => {
    const component = createComponent();
    expect(component.phase()).toBe('ready');
    expect(component.suggestedQuestions()).toEqual(['What are your hours?', 'How do I reset my password?']);
    expect(component.showEmptyState()).toBe(true);
  });

  it('selectSuggestedQuestion fills the draft and triggers send with that exact question', () => {
    const component = createComponent();

    component.selectSuggestedQuestion('What are your hours?');

    expect(askSpy).toHaveBeenCalledWith({ question: 'What are your hours?', conversation_id: null });
    // send() clears the draft once it has been submitted as a message.
    expect(component.draft()).toBe('');
  });

  it('adds a user message with the suggested question text when a chip is selected', () => {
    const component = createComponent();

    component.selectSuggestedQuestion('How do I reset my password?');

    const messages = component.messages();
    expect(messages.length).toBeGreaterThan(0);
    expect(messages[0]).toEqual(
      expect.objectContaining({ role: 'user', text: 'How do I reset my password?' }),
    );
  });

  it('hides the empty state (and therefore the suggestion chips) after the first message', () => {
    const component = createComponent();
    expect(component.showEmptyState()).toBe(true);

    component.selectSuggestedQuestion('What are your hours?');

    expect(component.showEmptyState()).toBe(false);
  });
});
