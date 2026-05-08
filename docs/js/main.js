// Agentic-J landing — small, dependency-free progressive enhancement.

// 1) Reveal-on-scroll
const io = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting) {
      e.target.classList.add('in');
      io.unobserve(e.target);
    }
  });
}, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

// 2) Copy-code buttons
document.querySelectorAll('.code [data-copy]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const pre = btn.closest('.code');
    if (!pre) return;
    const text = Array.from(pre.childNodes)
      .filter((n) => n !== btn)
      .map((n) => n.textContent || '')
      .join('')
      .trim();
    try {
      await navigator.clipboard.writeText(text);
      const old = btn.textContent;
      btn.textContent = 'copied ✓';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = old; btn.classList.remove('copied'); }, 1500);
    } catch {
      btn.textContent = 'press ⌘C';
    }
  });
});

// 3) Active nav link as you scroll
const sections = ['features', 'architecture', 'quickstart', 'plugins', 'docs']
  .map((id) => document.getElementById(id))
  .filter(Boolean);
const navLinks = new Map(
  Array.from(document.querySelectorAll('.nav-links a'))
    .filter((a) => a.getAttribute('href')?.startsWith('#'))
    .map((a) => [a.getAttribute('href').slice(1), a])
);
const navIO = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    navLinks.forEach((a) => a.style.color = '');
    const link = navLinks.get(e.target.id);
    if (link) link.style.color = 'var(--text)';
  });
}, { rootMargin: '-45% 0px -45% 0px' });
sections.forEach((s) => navIO.observe(s));
