import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OdooAccessService } from '../services/odoo-access.service';
import { odooAccessGuard } from './odoo-access.guard';

/**
 * Ask Odoo is shown/reachable only when the backend's GET /odoo/access says
 * so — company users with their own company's Odoo, or Vita Care staff.
 */
describe('odooAccessGuard / OdooAccessService', () => {
  const url = `${environment.apiBaseUrl}/odoo/access`;
  let httpMock: HttpTestingController;
  let access: OdooAccessService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
    access = TestBed.inject(OdooAccessService);
    router = TestBed.inject(Router);
  });

  afterEach(() => httpMock.verify());

  function runGuard(): Promise<boolean | UrlTree> {
    const result = TestBed.runInInjectionContext(() =>
      odooAccessGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    ) as Observable<boolean | UrlTree>;
    return firstValueFrom(result);
  }

  it('lets an allowed user through and shows the link', async () => {
    const result = runGuard();
    httpMock.expectOne(url).flush({ allowed: true, source: 'company', reason: null });
    expect(await result).toBe(true);
    expect(access.allowed()).toBe(true);
  });

  it('sends a refused user to /access-denied and hides the link', async () => {
    const result = runGuard();
    httpMock.expectOne(url).flush({ allowed: false, source: null, reason: "Ask Odoo isn't set up for your company yet" });
    expect(router.serializeUrl((await result) as UrlTree)).toBe('/access-denied');
    expect(access.allowed()).toBe(false);
  });

  it('treats a backend error (e.g. a non-Vita-Care tenant 403) as not allowed', async () => {
    const result = runGuard();
    httpMock.expectOne(url).flush({ detail: 'nope' }, { status: 403, statusText: 'Forbidden' });
    expect(router.serializeUrl((await result) as UrlTree)).toBe('/access-denied');
    expect(access.allowed()).toBe(false);
  });

  it('refresh() hides the link until the new answer arrives', () => {
    access.allowed.set(true); // previous user's answer
    access.refresh();
    expect(access.allowed()).toBe(false);
    httpMock.expectOne(url).flush({ allowed: true, source: 'vita_care', reason: null });
    expect(access.allowed()).toBe(true);
  });
});
