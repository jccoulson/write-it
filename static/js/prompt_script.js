//script to have a countdown timer


const mode = document.querySelector('input[name="mode"]').value;
let timeLeft; //countdown will be based on mode

//10, 15, and 20 minutes based on mode
switch (mode) {
    case 'normal':
        timeLeft = 60 * 10; 
        break;
    case 'creative':
        timeLeft = 60 * 15;
        break;
    case 'challenge':
        timeLeft = 60 * 20; 
        break;
    default:
        timeLeft = 60 * 10; 
        break;
}

function updateTimer() {
    let minutes = Math.floor(timeLeft / 60);
    let seconds = timeLeft % 60;
    //getting display from current time
    let timerDisplay = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    //change the timer element to cur time
    document.getElementById('timer').textContent = timerDisplay;
    if (timeLeft > 0) {
        timeLeft--;
    } else {
        clearInterval(timerInterval);
        //when timer is done move to analysis page
        document.getElementById('essayForm').submit();
    }
}

let timerInterval = setInterval(updateTimer, 1000);



//adding a minimum and maximum char to essay submitted
document.addEventListener('DOMContentLoaded', function() {
    const essayForm = document.getElementById('essayForm');
    const textarea = document.querySelector('textarea[name="inputEssay"]');
    const charCount = document.getElementById('charCount');
    const validationMessage = document.getElementById('validationMessage');
    //4000 characters max, 750 min
    const maxLength = 4000;
    const minLength = 750;

    //show how many chars they have done so far
    textarea.addEventListener('input', function() {
        const currentLength = textarea.value.length;
        charCount.textContent = `${currentLength} / ${maxLength}`;
    });

    //create an error message if they have invalid number of characters
    essayForm.addEventListener('submit', function(event) {
        const currentLength = textarea.value.length;
        if (currentLength < minLength || currentLength > maxLength) {
            event.preventDefault(); //submission is prevented
            //display message based on current scenario
            if (currentLength < minLength) {
                validationMessage.textContent = 'Please add more text. Minimum required characters: 750.';
            } else if (currentLength > maxLength) {
                validationMessage.textContent = 'Too much text. Maximum allowed characters: 4000.';
            }
        } else {
            validationMessage.textContent = ''; //make sure no message if clear
        }
    });
});