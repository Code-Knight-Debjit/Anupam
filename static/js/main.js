/* ============================================================
   ANUPAM BEARINGS — PREMIUM ANIMATION & INTERACTION SYSTEM
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

  /* ── INTRO OVERLAY ── */
  const intro = document.getElementById('intro-overlay');
  if (intro) {
    const seen = sessionStorage.getItem('ab_intro_seen');
    if (seen) {
      intro.style.display = 'none';
    } else {
      const duration = window.innerWidth < 768 ? 2600 : 3400;
      setTimeout(() => {
        intro.classList.add('fade-out');
        intro.addEventListener('animationend', () => {
          intro.style.display = 'none';
          sessionStorage.setItem('ab_intro_seen', '1');
        }, { once: true });
      }, duration);
    }
  }

  /* ── NAVBAR SCROLL ── */
  const navbar = document.getElementById('navbar');
  const scrollProgress = document.getElementById('scroll-progress');

  const handleScroll = () => {
    const scrolled = window.scrollY;
    const total = document.documentElement.scrollHeight - window.innerHeight;

    if (navbar) {
      navbar.classList.toggle('scrolled', scrolled > 60);
    }
    if (scrollProgress && total > 0) {
      scrollProgress.style.width = `${(scrolled / total) * 100}%`;
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });

  /* ── MOBILE NAV ── */
  const hamburger = document.getElementById('hamburger');
  const mobileNav = document.getElementById('mobile-nav');

  if (hamburger && mobileNav) {
    hamburger.addEventListener('click', () => {
      hamburger.classList.toggle('open');
      mobileNav.classList.toggle('open');
      document.body.style.overflow = mobileNav.classList.contains('open') ? 'hidden' : '';
    });

    mobileNav.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        hamburger.classList.remove('open');
        mobileNav.classList.remove('open');
        document.body.style.overflow = '';
      });
    });

    const mobileClose = document.getElementById('mobile-close');
    if (mobileClose) {
      mobileClose.addEventListener('click', () => {
        hamburger.classList.remove('open');
        mobileNav.classList.remove('open');
        document.body.style.overflow = '';
      });
    }
  }

  /* ── ACTIVE NAV LINK ── */
  const currentPath = window.location.pathname;
  document.querySelectorAll('.nav-links a, .nav-mobile a').forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
      link.classList.add('active');
    }
  });

  /* ── GSAP SCROLL ANIMATIONS (with fallback) ── */
  if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);

    // Fade up elements
    gsap.utils.toArray('.anim-fade-up').forEach((el, i) => {
      const delay = parseFloat(el.dataset.delay || 0);
      gsap.to(el, {
        opacity: 1,
        y: 0,
        duration: 0.75,
        delay,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: el,
          start: 'top 88%',
          once: true,
        }
      });
    });

    // Staggered groups
    gsap.utils.toArray('.anim-stagger-group').forEach(group => {
      const children = group.querySelectorAll('.anim-stagger-child');
      gsap.to(children, {
        opacity: 1,
        y: 0,
        duration: 0.7,
        stagger: 0.12,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: group,
          start: 'top 85%',
          once: true,
        }
      });
    });

    // Slide left
    gsap.utils.toArray('.anim-slide-left').forEach(el => {
      gsap.to(el, {
        opacity: 1,
        x: 0,
        duration: 0.8,
        ease: 'power3.out',
        scrollTrigger: { trigger: el, start: 'top 85%', once: true }
      });
    });

    // Slide right
    gsap.utils.toArray('.anim-slide-right').forEach(el => {
      gsap.to(el, {
        opacity: 1,
        x: 0,
        duration: 0.8,
        ease: 'power3.out',
        scrollTrigger: { trigger: el, start: 'top 85%', once: true }
      });
    });

    // Scale in
    gsap.utils.toArray('.anim-scale').forEach((el, i) => {
      const delay = parseFloat(el.dataset.delay || 0);
      gsap.to(el, {
        opacity: 1,
        scale: 1,
        duration: 0.65,
        delay,
        ease: 'back.out(1.4)',
        scrollTrigger: { trigger: el, start: 'top 88%', once: true }
      });
    });

    // Hero parallax
    const heroBg = document.querySelector('.bearing-hero-svg');
    if (heroBg) {
      gsap.to(heroBg, {
        y: 60,
        ease: 'none',
        scrollTrigger: {
          trigger: '.hero-section',
          start: 'top top',
          end: 'bottom top',
          scrub: true,
        }
      });
    }

    // Counter animation
    gsap.utils.toArray('.stat-number[data-count]').forEach(el => {
      const target = parseInt(el.dataset.count);
      gsap.fromTo(el, { innerText: 0 }, {
        innerText: target,
        duration: 2,
        ease: 'power2.out',
        snap: { innerText: 1 },
        scrollTrigger: { trigger: el, start: 'top 85%', once: true },
        onUpdate: function () { el.textContent = Math.round(this.targets()[0].innerText) + (el.dataset.suffix || ''); }
      });
    });

  } else {
    // CSS fallback for scroll animations
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const el = entry.target;
          el.style.transition = 'opacity 0.75s ease, transform 0.75s ease';
          el.style.opacity = '1';
          el.style.transform = 'translateY(0) translateX(0) scale(1)';
          observer.unobserve(el);
        }
      });
    }, { threshold: 0.1 });

    document.querySelectorAll('.anim-fade-up, .anim-slide-left, .anim-slide-right, .anim-scale, .anim-fade-in').forEach(el => {
      observer.observe(el);
    });

    // Staggered groups
    const staggerObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const children = entry.target.querySelectorAll('.anim-stagger-child');
          children.forEach((child, i) => {
            setTimeout(() => {
              child.style.transition = 'opacity 0.7s ease, transform 0.7s ease';
              child.style.opacity = '1';
              child.style.transform = 'translateY(0)';
            }, i * 120);
          });
          staggerObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll('.anim-stagger-group').forEach(el => staggerObserver.observe(el));
  }

  /* ── HERO SLIDER ── */
  const heroSection = document.querySelector('.hero-section');
  if (heroSection) {
    const slides = heroSection.querySelectorAll('.hero-slide');
    const dots = heroSection.querySelectorAll('.slider-dot');
    let current = 0;
    let interval;

    const goTo = (idx) => {
      slides[current].classList.remove('active');
      dots[current]?.classList.remove('active');
      current = (idx + slides.length) % slides.length;
      slides[current].classList.add('active');
      dots[current]?.classList.add('active');
    };

    const startAuto = () => { interval = setInterval(() => goTo(current + 1), 5000); };
    const stopAuto = () => clearInterval(interval);

    dots.forEach((dot, i) => {
      dot.addEventListener('click', () => { stopAuto(); goTo(i); startAuto(); });
    });

    const prevBtn = heroSection.querySelector('.slider-arrow.prev');
    const nextBtn = heroSection.querySelector('.slider-arrow.next');
    prevBtn?.addEventListener('click', () => { stopAuto(); goTo(current - 1); startAuto(); });
    nextBtn?.addEventListener('click', () => { stopAuto(); goTo(current + 1); startAuto(); });

    // Touch swipe
    let touchStartX = 0;
    heroSection.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; }, { passive: true });
    heroSection.addEventListener('touchend', e => {
      const diff = touchStartX - e.changedTouches[0].clientX;
      if (Math.abs(diff) > 50) { stopAuto(); goTo(current + (diff > 0 ? 1 : -1)); startAuto(); }
    }, { passive: true });

    goTo(0);
    startAuto();
  }

  /* ── PRODUCT CATEGORY TABS ── */
  const catTabs = document.querySelectorAll('.cat-tab');
  if (catTabs.length) {
    catTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        catTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const catId = tab.dataset.cat;

        document.querySelectorAll('.products-section').forEach(section => {
          const isTarget = catId === 'all' || section.dataset.cat === catId;
          section.style.display = isTarget ? 'block' : 'none';
          if (isTarget && typeof gsap !== 'undefined') {
            gsap.fromTo(section.querySelectorAll('.product-card'),
              { opacity: 0, y: 20 },
              { opacity: 1, y: 0, stagger: 0.08, duration: 0.5, ease: 'power3.out' }
            );
          }
        });
      });
    });
  }

  /* ── MOBILE PRODUCT ACCORDION ── */
  document.querySelectorAll('.accordion-trigger').forEach(trigger => {
    trigger.addEventListener('click', () => {
      const content = trigger.nextElementSibling;
      const isOpen = trigger.classList.contains('open');
      document.querySelectorAll('.accordion-trigger.open').forEach(t => {
        t.classList.remove('open');
        t.nextElementSibling.style.maxHeight = '0';
      });
      if (!isOpen) {
        trigger.classList.add('open');
        content.style.maxHeight = content.scrollHeight + 'px';
      }
    });
  });

  /* ── ENQUIRY MODAL ── */
  const enquiryModal = document.getElementById('enquiry-modal');
  const enquiryForm = document.getElementById('enquiry-form');

  document.querySelectorAll('[data-enquire]').forEach(btn => {
    btn.addEventListener('click', () => {
      const productId = btn.dataset.enquire;
      const productName = btn.dataset.name;
      if (enquiryModal) {
        enquiryModal.querySelector('#modal-product-name').textContent = productName || 'Product';
        enquiryModal.querySelector('[name="product_id"]').value = productId || '';
        enquiryModal.classList.add('open');
        document.body.style.overflow = 'hidden';
      }
    });
  });

  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeAllModals();
    });
  });
  document.querySelectorAll('.modal-close').forEach(btn => {
    btn.addEventListener('click', closeAllModals);
  });

  function closeAllModals() {
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
    document.body.style.overflow = '';
  }

  if (enquiryForm) {
    enquiryForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(enquiryForm);
      const data = Object.fromEntries(fd);
      const submitBtn = enquiryForm.querySelector('[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Sending...';
      try {
        const res = await fetch('/products/enquire/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify(data),
        });
        const result = await res.json();
        if (result.success) {
          showToast('Enquiry sent successfully!', 'success');
          closeAllModals();
          enquiryForm.reset();
        } else {
          showToast(result.message || 'Failed to send. Try again.', 'error');
        }
      } catch {
        showToast('Network error. Please try again.', 'error');
      }
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send Enquiry';
    });
  }

  /* ── CONTACT FORM ── */
  const contactForm = document.getElementById('contact-form');
  if (contactForm) {
    contactForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(contactForm);
      const data = Object.fromEntries(fd);
      const submitBtn = contactForm.querySelector('[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Sending...';
      try {
        const res = await fetch('/contact/send/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify(data),
        });
        const result = await res.json();
        if (result.success) {
          showToast('Message sent! We\'ll get back to you soon.', 'success');
          contactForm.reset();
        } else {
          showToast('Failed to send. Please try again.', 'error');
        }
      } catch {
        showToast('Network error. Please try again.', 'error');
      }
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send Message';
    });
  }

  /* ── CHATBOT ── */
  const chatBtn = document.getElementById('chatbot-btn');
  const chatPanel = document.getElementById('chatbot-panel');
  const chatClose = document.getElementById('chatbot-close');
  const chatInput = document.getElementById('chatbot-input');
  const chatSend = document.getElementById('chatbot-send');
  const chatMessages = document.getElementById('chatbot-messages');
  let chatHistory = [];

  if (chatBtn && chatPanel) {
    chatBtn.addEventListener('click', () => {
      chatPanel.classList.toggle('open');
      if (chatPanel.classList.contains('open')) {
        if (chatMessages.children.length === 0) addAssistantMessage("Hi! I'm Anupam Assistant 👋 I can help you with product information, specifications, and enquiries. How can I assist you today?");
        setTimeout(() => chatInput?.focus(), 300);
      }
    });

    chatClose?.addEventListener('click', () => chatPanel.classList.remove('open'));

    const sendMessage = async () => {
      const msg = chatInput.value.trim();
      if (!msg) return;

      // Disable input while processing
      chatInput.value = '';
      chatInput.disabled = true;
      chatSend.disabled = true;

      addUserMessage(msg);
      chatHistory.push({ role: 'user', content: msg });
      const typingEl = showTyping();

      try {
        // Step 1: Enqueue async task — returns immediately with task_id
        const enqueueRes = await fetch('/api/chat/async/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({ message: msg, history: chatHistory }),
        });

        if (enqueueRes.status === 429) {
          typingEl.remove();
          addAssistantMessage("You're sending messages too quickly. Please wait a moment and try again.");
          return;
        }

        const enqueueData = await enqueueRes.json();

        if (!enqueueData.success || !enqueueData.task_id) {
          typingEl.remove();
          addAssistantMessage(enqueueData.reply || "Sorry, I couldn't process that. Please contact us directly.");
          return;
        }

        // Step 2: Poll for result with exponential backoff
        const taskId = enqueueData.task_id;
        let reply = null;
        let attempts = 0;
        const maxAttempts = 30; // 30 × ~1.5s avg = ~45s max wait

        while (attempts < maxAttempts) {
          await new Promise(r => setTimeout(r, attempts < 5 ? 800 : 1500));
          attempts++;

          try {
            const pollRes  = await fetch(`/api/chat/result/${taskId}/`);
            const pollData = await pollRes.json();

            if (pollData.status === 'success') {
              reply = pollData.reply;
              break;
            } else if (pollData.status === 'failure') {
              reply = "I encountered an error. Please contact us at info@anupambearings.com.";
              break;
            }
            // 'pending' or 'processing' → keep polling
          } catch {
            // network blip — retry
          }
        }

        typingEl.remove();

        if (!reply) {
          reply = "The response is taking too long. Please try again or contact us at +91-98844-00741.";
        }

        addAssistantMessage(reply);
        chatHistory.push({ role: 'assistant', content: reply });

      } catch (err) {
        typingEl.remove();
        addAssistantMessage("I'm having connection issues. Please call us at +91-98844-00741.");
      } finally {
        chatInput.disabled = false;
        chatSend.disabled  = false;
        chatInput.focus();
      }
    };

    chatSend?.addEventListener('click', sendMessage);
    chatInput?.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
  }

  function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'chat-msg user';
    div.textContent = text;
    chatMessages?.appendChild(div);
    scrollChat();
  }

  function addAssistantMessage(text) {
    const div = document.createElement('div');
    div.className = 'chat-msg assistant';
    div.textContent = text;
    chatMessages?.appendChild(div);
    scrollChat();
  }

  function showTyping() {
    const div = document.createElement('div');
    div.className = 'chat-msg typing';
    div.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    chatMessages?.appendChild(div);
    scrollChat();
    return div;
  }

  function scrollChat() {
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  /* ── TOAST ── */
  function showToast(message, type = 'success') {
    let toast = document.getElementById('global-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'global-toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = `toast ${type}`;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => toast.classList.add('show'));
    });
    setTimeout(() => toast.classList.remove('show'), 4000);
  }

  /* ── CSRF ── */
  function getCsrf() {
    return document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='))?.split('=')[1] || '';
  }

  /* ── GALLERY LIGHTBOX ── */
  document.querySelectorAll('.gallery-item').forEach(item => {
    item.addEventListener('click', () => {
      const src = item.querySelector('img')?.src;
      if (!src) return;
      const lb = document.createElement('div');
      lb.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:zoom-out;';
      const img = document.createElement('img');
      img.src = src;
      img.style.cssText = 'max-width:90vw;max-height:90vh;object-fit:contain;border-radius:4px;';
      lb.appendChild(img);
      lb.addEventListener('click', () => lb.remove());
      document.body.appendChild(lb);
    });
  });

  /* ── CURSOR GLOW (desktop only) ── */
  if (window.innerWidth > 1024) {
    const glow = document.createElement('div');
    glow.style.cssText = 'position:fixed;width:300px;height:300px;border-radius:50%;background:radial-gradient(circle,rgba(255,106,0,0.04) 0%,transparent 70%);pointer-events:none;z-index:0;transform:translate(-50%,-50%);transition:left 0.3s ease,top 0.3s ease;';
    document.body.appendChild(glow);
    window.addEventListener('mousemove', e => {
      glow.style.left = e.clientX + 'px';
      glow.style.top = e.clientY + 'px';
    }, { passive: true });
  }

});

/* ── LIVE PRODUCT SEARCH ── */
(function () {
  const searchInput = document.getElementById('product-search-input');
  const searchResults = document.getElementById('product-search-results');
  if (!searchInput || !searchResults) return;

  let debounceTimer;
  let activeIndex = -1;

  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = searchInput.value.trim();
    if (q.length < 2) { searchResults.style.display = 'none'; return; }
    debounceTimer = setTimeout(() => fetchResults(q), 280);
  });

  searchInput.addEventListener('keydown', e => {
    const items = searchResults.querySelectorAll('.search-result-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      items.forEach((el, i) => el.classList.toggle('active', i === activeIndex));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, -1);
      items.forEach((el, i) => el.classList.toggle('active', i === activeIndex));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      items[activeIndex]?.click();
    } else if (e.key === 'Escape') {
      searchResults.style.display = 'none';
      activeIndex = -1;
    }
  });

  document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
      searchResults.style.display = 'none';
    }
  });

  async function fetchResults(q) {
    try {
      const res  = await fetch(`/products/search/?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      renderResults(data.results, q);
    } catch { searchResults.style.display = 'none'; }
  }

  function renderResults(results, q) {
    activeIndex = -1;
    if (!results.length) {
      searchResults.innerHTML = '<div class="search-no-result">No products found for "' + q + '"</div>';
      searchResults.style.display = 'block';
      return;
    }
    searchResults.innerHTML = results.map(r => `
      <a href="${r.url}" class="search-result-item">
        <div class="search-result-icon">${r.icon || '⚙️'}</div>
        <div>
          <div class="search-result-name">${highlight(r.name, q)}</div>
          <div class="search-result-cat">${r.category}</div>
        </div>
      </a>
    `).join('') + `<div class="search-result-footer"><a href="/products/search/?q=${encodeURIComponent(q)}">View all results →</a></div>`;
    searchResults.style.display = 'block';
  }

  function highlight(text, q) {
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return text.replace(re, '<mark style="background:rgba(255,106,0,.2);color:inherit;border-radius:2px;">$1</mark>');
  }
}());
