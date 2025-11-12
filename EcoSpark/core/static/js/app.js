/**
 * EcoSpark Main JavaScript
 * Handles AOS initialization and smooth scrolling
 */
document.addEventListener('DOMContentLoaded', () => {
	// Initialize AOS (Animate On Scroll)
	if (window.AOS) {
		AOS.init({
			duration: 800,
			once: true,
			offset: 100,
			easing: 'ease-out-cubic',
		});
	}
	
	// Smooth scroll for in-page anchors
	document.querySelectorAll('a[href^="#"]').forEach(a => {
		a.addEventListener('click', (e) => {
			const id = a.getAttribute('href');
			if (id.length > 1 && document.querySelector(id)) {
				e.preventDefault();
				const target = document.querySelector(id);
				const offset = 80; // Account for sticky navbar
				const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - offset;
				window.scrollTo({
					top: targetPosition,
					behavior: 'smooth'
				});
			}
		});
	});
	
	// Ensure content is always visible - no fade-in that hides content
	document.body.style.opacity = '1';
	document.body.style.visibility = 'visible';
});


