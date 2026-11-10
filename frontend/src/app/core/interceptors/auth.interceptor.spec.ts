import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { authInterceptor } from './auth.interceptor';

/** The session lives in an httpOnly cookie, so every API request must send credentials. */
describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('sets withCredentials so the session cookie is sent', () => {
    http.get('http://localhost:8000/auth/me').subscribe();
    const req = httpMock.expectOne('http://localhost:8000/auth/me');
    expect(req.request.withCredentials).toBe(true);
    req.flush({});
  });
});
