/**
 * EcoSpark Theme & Animation Controller
 * Handles dark/light theme toggle and floating particles animation
 */

(function() {
    'use strict';

    // ============================================
    // Theme Toggle Functionality
    // ============================================
    
    /**
     * Initialize theme based on system preference or saved preference
     */
    function initTheme() {
        const savedTheme = localStorage.getItem('ecospark-theme');
        const html = document.documentElement;
        
        if (savedTheme) {
            html.setAttribute('data-theme', savedTheme);
        } else {
            // Use system preference
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            html.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
        }
        
        updateThemeButton();
    }

    /**
     * Toggle between light and dark theme
     */
    function toggleTheme() {
        const html = document.documentElement;
        const currentTheme = html.getAttribute('data-theme') || 'auto';
        let newTheme;
        
        if (currentTheme === 'dark') {
            newTheme = 'light';
        } else if (currentTheme === 'light') {
            newTheme = 'dark';
        } else {
            // If auto, check system preference
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            newTheme = prefersDark ? 'light' : 'dark';
        }
        
        html.setAttribute('data-theme', newTheme);
        localStorage.setItem('ecospark-theme', newTheme);
        updateThemeButton();
    }

    /**
     * Update theme toggle button icon
     */
    function updateThemeButton() {
        const button = document.getElementById('themeToggle');
        if (!button) return;
        
        const html = document.documentElement;
        const currentTheme = html.getAttribute('data-theme') || 'auto';
        const isDark = currentTheme === 'dark' || 
                      (currentTheme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
        
        button.textContent = isDark ? '☀️' : '🌙';
    }

    // ============================================
    // Floating Particles Animation
    // ============================================
    
    /**
     * Create floating particles for background animation
     */
    function createParticles() {
        const container = document.getElementById('particles');
        if (!container) return;
        
        const particleCount = 15; // Adjust based on performance
        const particles = [];
        
        // Create particles
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            
            // Random size between 50px and 150px
            const size = Math.random() * 100 + 50;
            particle.style.width = size + 'px';
            particle.style.height = size + 'px';
            particle.style.position = 'absolute';
            
            // Random starting position (absolute pixels)
            const startX = Math.random() * (window.innerWidth - size);
            const startY = Math.random() * (window.innerHeight - size);
            particle.style.left = startX + 'px';
            particle.style.top = startY + 'px';
            
            container.appendChild(particle);
            particles.push(particle);
        }
        
        // Animate particles with requestAnimationFrame for smoother movement
        animateParticles(particles);
    }

    /**
     * Animate particles with smooth random movement and collision detection
     */
    function animateParticles(particles) {
        let lastTime = performance.now();
        
        // Store particle data with velocity
        const particleData = particles.map((particle, index) => {
            const rect = particle.getBoundingClientRect();
            const size = parseFloat(particle.style.width) || 80;
            return {
                element: particle,
                x: rect.left + size / 2,
                y: rect.top + size / 2,
                vx: (Math.random() - 0.5) * 0.08, // Very slow velocity (0.08 pixels per frame)
                vy: (Math.random() - 0.5) * 0.08,
                radius: size / 2,
                index: index
            };
        });
        
        function animate(currentTime) {
            const deltaTime = Math.min((currentTime - lastTime) / 16.67, 2); // Cap deltaTime
            lastTime = currentTime;
            
            // Update positions
            particleData.forEach((p, index) => {
                // Very slow movement
                p.x += p.vx * deltaTime;
                p.y += p.vy * deltaTime;
                
                // Boundary collision with bounce
                if (p.x - p.radius < 0 || p.x + p.radius > window.innerWidth) {
                    p.vx *= -0.8; // Bounce with slight damping
                    p.x = Math.max(p.radius, Math.min(window.innerWidth - p.radius, p.x));
                }
                if (p.y - p.radius < 0 || p.y + p.radius > window.innerHeight) {
                    p.vy *= -0.8;
                    p.y = Math.max(p.radius, Math.min(window.innerHeight - p.radius, p.y));
                }
                
                // Particle-to-particle collision detection
                particleData.forEach((other, otherIndex) => {
                    if (index >= otherIndex) return; // Avoid duplicate checks
                    
                    const dx = other.x - p.x;
                    const dy = other.y - p.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    const minDistance = p.radius + other.radius;
                    
                    if (distance < minDistance && distance > 0) {
                        // Collision detected - separate particles
                        const angle = Math.atan2(dy, dx);
                        const overlap = minDistance - distance;
                        
                        // Move particles apart
                        const moveX = Math.cos(angle) * overlap * 0.5;
                        const moveY = Math.sin(angle) * overlap * 0.5;
                        p.x -= moveX;
                        p.y -= moveY;
                        other.x += moveX;
                        other.y += moveY;
                        
                        // Exchange velocities (elastic collision)
                        const relativeVx = other.vx - p.vx;
                        const relativeVy = other.vy - p.vy;
                        const dotProduct = relativeVx * Math.cos(angle) + relativeVy * Math.sin(angle);
                        
                        if (dotProduct < 0) {
                            const impulse = 2 * dotProduct;
                            p.vx += impulse * Math.cos(angle) * 0.3; // Damping factor
                            p.vy += impulse * Math.sin(angle) * 0.3;
                            other.vx -= impulse * Math.cos(angle) * 0.3;
                            other.vy -= impulse * Math.sin(angle) * 0.3;
                        }
                    }
                });
                
                // Update DOM position
                p.element.style.left = (p.x - p.radius) + 'px';
                p.element.style.top = (p.y - p.radius) + 'px';
                
                // Subtle opacity variation
                const opacity = 0.03 + Math.sin(currentTime / 5000 + index) * 0.02;
                p.element.style.opacity = opacity;
            });
            
            requestAnimationFrame(animate);
        }
        
        requestAnimationFrame(animate);
        
        // Handle window resize
        window.addEventListener('resize', () => {
            particleData.forEach(p => {
                if (p.x > window.innerWidth) p.x = window.innerWidth - p.radius;
                if (p.y > window.innerHeight) p.y = window.innerHeight - p.radius;
            });
        });
    }

    // ============================================
    // Lazy Load Images
    // ============================================
    
    /**
     * Lazy load images with blur effect
     */
    function initLazyLoad() {
        const images = document.querySelectorAll('img[loading="lazy"]');
        
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.addEventListener('load', () => {
                            img.classList.add('loaded');
                        });
                        observer.unobserve(img);
                    }
                });
            });
            
            images.forEach(img => imageObserver.observe(img));
        } else {
            // Fallback for older browsers
            images.forEach(img => {
                img.addEventListener('load', () => {
                    img.classList.add('loaded');
                });
            });
        }
    }

    // ============================================
    // Active Nav Link Highlighting
    // ============================================
    
    /**
     * Highlight active navigation link based on current URL
     */
    function highlightActiveNav() {
        const currentPath = window.location.pathname;
        const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
        
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href && currentPath.startsWith(href) && href !== '/') {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // ============================================
    // Initialize Everything
    // ============================================
    
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize theme (auto-detect, no manual toggle)
        initTheme();
        
        // Listen for system theme changes (auto-adapt)
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            const html = document.documentElement;
            if (!localStorage.getItem('ecospark-theme')) {
                html.setAttribute('data-theme', e.matches ? 'dark' : 'light');
            }
        });
        
        // Create floating particles
        createParticles();
        
        // Initialize lazy loading
        initLazyLoad();
        
        // Highlight active nav
        highlightActiveNav();
        
        // Add smooth page transitions
        document.querySelectorAll('a[href^="/"]').forEach(link => {
            link.addEventListener('click', function(e) {
                // Only for internal links
                if (this.hostname === window.location.hostname) {
                    document.body.style.opacity = '0.95';
                    setTimeout(() => {
                        document.body.style.opacity = '1';
                    }, 100);
                }
            });
        });
    });

    // ============================================
    // Parallax Effect for Hero (on scroll)
    // ============================================
    
    window.addEventListener('scroll', function() {
        const hero = document.querySelector('.hero-green');
        if (!hero) return;
        
        const scrolled = window.pageYOffset;
        const parallax = scrolled * 0.5;
        
        hero.style.transform = `translateY(${parallax}px)`;
    });

})();

