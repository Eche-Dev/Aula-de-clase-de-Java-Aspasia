/**
 * Salto al Checkout de Stripe (Fase B/Fase D).
 *
 * La tarjeta se teclea SIEMPRE en la página de Stripe: aquí solo
 * redirigimos el navegador a la `checkout_url` que devuelve el backend.
 */
export function redirectToCheckout(url: string): void {
  window.location.assign(url);
}
