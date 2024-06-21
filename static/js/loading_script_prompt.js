const forms = document.querySelectorAll('form');

forms.forEach(form => {
    form.addEventListener('submit', function() {
        //delays the loading message by 2 seconds
        setTimeout(function() {
            var loading_message = document.getElementById('loading_message');
            if (loading_message) loading_message.classList.remove('hidden');
            animateEllipses(loading_message);
        }, 2000);
    });
});

function animateEllipses(loading_element) {
    let dots = 0;
    let baseText = "Good job! Analyzing your text for feedback";
    loading_element.textContent = baseText + '...'; 

    let interval = setInterval(() => {
        dots = (dots + 1) % 4; //cycles through the ellipses .  ..  ...   .  ..  ...
        let dot_string = '.'.repeat(dots); //repeats the ellipses based dots variable, then turns into a string
        loading_element.textContent = baseText + dot_string;
    }, 750); //how often the dots change
}