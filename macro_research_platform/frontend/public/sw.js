/**
 * Service Worker for Macro Research Platform
 *
 * Handles browser push notifications for alerts.
 */

const CACHE_NAME = 'macro-platform-v1';

// Install event - cache assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // FIXED: Only cache files that exist (avoid 404 errors)
      return cache.addAll(['/']).catch(err => {
        console.log('[SW] Some assets failed to cache:', err);
      });
    })
  );
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Push notification event
self.addEventListener('push', (event) => {
  if (!event.data) return;

  try {
    const data = event.data.json();
    const options = {
      body: data.message || 'New alert from Macro Research Platform',
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      tag: data.id || 'alert',
      requireInteraction: data.severity === 'critical',
      data: {
        url: data.url || '/',
        severity: data.severity,
        category: data.category,
      },
      actions: [
        { action: 'view', title: 'View Dashboard' },
        { action: 'dismiss', title: 'Dismiss' },
      ],
    };

    event.waitUntil(
      self.registration.showNotification(
        data.title || 'Macro Research Platform',
        options
      )
    );
  } catch (error) {
    console.error('Push notification error:', error);
  }
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const { action } = event;
  const { url } = event.notification.data || {};

  if (action === 'view' || !action) {
    // Focus or open window
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
        if (clientList.length > 0) {
          const client = clientList[0];
          client.focus();
          if (url) {
            client.navigate(url);
          }
        } else {
          clients.openWindow(url || '/');
        }
      })
    );
  }
  // If action === 'dismiss', just close (already done above)
});

// Message from main thread
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
