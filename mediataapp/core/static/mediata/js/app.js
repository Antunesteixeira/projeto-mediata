(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebarToggle');
    const backdrop = document.getElementById('sidebarBackdrop');
    const content = document.getElementById('mainContent');
    if (!sidebar || !toggle || !content) return;

    const mobile = window.matchMedia('(max-width: 768px)');
    const readCollapsed = () => {
      try { return localStorage.getItem('sidebarCollapsed') === 'true'; }
      catch { return false; }
    };
    const saveCollapsed = collapsed => {
      try { localStorage.setItem('sidebarCollapsed', String(collapsed)); }
      catch { /* A navegação continua funcionando sem armazenamento local. */ }
    };
    const closeMobile = () => {
      sidebar.classList.remove('show');
      document.body.classList.remove('sidebar-open');
      if (backdrop) backdrop.hidden = true;
      if (mobile.matches) toggle.setAttribute('aria-expanded', 'false');
    };
    const updateLayout = () => {
      closeMobile();
      const collapsed = !mobile.matches && readCollapsed();
      sidebar.classList.toggle('collapsed', collapsed);
      content.classList.toggle('expanded', collapsed);
      toggle.setAttribute('aria-expanded', String(!mobile.matches && !collapsed));
    };
    toggle.addEventListener('click', () => {
      if (mobile.matches) {
        const open = !sidebar.classList.contains('show');
        sidebar.classList.toggle('show', open);
        document.body.classList.toggle('sidebar-open', open);
        if (backdrop) backdrop.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
      } else {
        const collapsed = !sidebar.classList.contains('collapsed');
        sidebar.classList.toggle('collapsed', collapsed);
        content.classList.toggle('expanded', collapsed);
        saveCollapsed(collapsed);
        toggle.setAttribute('aria-expanded', String(!collapsed));
      }
    });
    if (backdrop) backdrop.addEventListener('click', closeMobile);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && mobile.matches) closeMobile();
    });
    sidebar.querySelectorAll('a:not([data-bs-toggle])').forEach(link => {
      link.addEventListener('click', () => { if (mobile.matches) closeMobile(); });
    });
    sidebar.querySelectorAll('[data-bs-toggle="collapse"]').forEach(link => {
      link.addEventListener('click', event => {
        if (mobile.matches || !sidebar.classList.contains('collapsed')) return;
        event.preventDefault();
        event.stopPropagation();
        sidebar.classList.remove('collapsed');
        content.classList.remove('expanded');
        saveCollapsed(false);
        toggle.setAttribute('aria-expanded', 'true');
        const target = document.querySelector(link.getAttribute('href'));
        if (target && window.bootstrap) bootstrap.Collapse.getOrCreateInstance(target, { toggle: false }).show();
      });
    });
    mobile.addEventListener('change', updateLayout);
    updateLayout();

    const path = window.location.pathname.replace(/\/$/, '');
    const links = Array.from(sidebar.querySelectorAll('.nav-link'));
    const exact = links.find(link => {
      const href = link.getAttribute('href');
      return href && !href.startsWith('#') && new URL(href, location.origin).pathname.replace(/\/$/, '') === path;
    });
    const section = links.find(link => (link.dataset.navPrefix || '').split(',').filter(Boolean).some(prefix => `${path}/`.startsWith(prefix)));
    [section, exact].filter(Boolean).forEach(link => link.classList.add('active'));
    const current = exact || section;
    if (current) current.setAttribute('aria-current', 'page');
    const submenu = exact && exact.closest('.collapse');
    if (submenu && window.bootstrap) {
      bootstrap.Collapse.getOrCreateInstance(submenu, { toggle: false }).show();
      const parent = sidebar.querySelector(`[href="#${submenu.id}"]`);
      if (parent) { parent.classList.add('active'); parent.setAttribute('aria-expanded', 'true'); }
    }
  });
})();
