import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { authInterceptor } from './auth.interceptor';
import { WidgetSessionService } from '../services/widget-session.service';

/**
 * Regression coverage for the CORS-credentials bug found while testing the
 * widget's suggested-questions feature: authInterceptor used to force
 * withCredentials on every request unconditionally, which the browser
 * rejects for /widget/* responses (routers/widget.py's widget_cors_middleware
 * never returns Access-Control-Allow-Credentials, by design — the widget is
 * Bearer-only, never cookies).
 */
describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let widgetSession: WidgetSessionService;

  function setup(widgetToken: string | null): void {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: WidgetSessionService, useValue: { token: widgetToken } },
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    widgetSession = TestBed.inject(WidgetSessionService);
  }

  afterEach(() => httpMock.verify());

  it('does not set withCredentials on a /widget/* request', () => {
    setup(null);
    http.get('http://localhost:8000/widget/config?tenant=creditplus').subscribe();
    const req = httpMock.expectOne('http://localhost:8000/widget/config?tenant=creditplus');
    expect(req.request.withCredentials).toBe(false);
    req.flush({});
  });

  it('does not set withCredentials on a non-widget URL once a widget session token exists', () => {
    setup('a-widget-bearer-token');
    http.post('http://localhost:8000/ask', { question: 'hi' }).subscribe();
    const req = httpMock.expectOne('http://localhost:8000/ask');
    expect(req.request.withCredentials).toBe(false);
    req.flush({});
  });

  it('still sets withCredentials on ordinary (non-widget) requests, preserving cookie-based auth', () => {
    setup(null);
    http.get('http://localhost:8000/auth/me').subscribe();
    const req = httpMock.expectOne('http://localhost:8000/auth/me');
    expect(req.request.withCredentials).toBe(true);
    req.flush({});
  });
});
