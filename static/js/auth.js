// Handle authentication forms and UI enhancements
document.addEventListener('DOMContentLoaded', function() {
    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading...';
            submitBtn.disabled = true;
            
            // Re-enable after 3 seconds if no response
            setTimeout(() => {
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }, 3000);
        });
    });

    // Password show/hide toggle
    const passwordFields = document.querySelectorAll('input[type="password"]');
    passwordFields.forEach(field => {
        field.insertAdjacentHTML('afterend', 
            '<i class="fas fa-eye toggle-password float-end"></i>');
    });

    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('toggle-password')) {
            const passwordField = e.target.previousElementSibling;
            if (passwordField.type === 'password') {
                passwordField.type = 'text';
                e.target.classList.remove('fa-eye');
                e.target.classList.add('fa-eye-slash');
            } else {
                passwordField.type = 'password';
                e.target.classList.remove('fa-eye-slash');
                e.target.classList.add('fa-eye');
            }
        }
    });
});
