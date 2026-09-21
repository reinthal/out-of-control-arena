This project tries to answer the following question:

> How good are current AIs at playing cyber defense compared to offense

For example, could a defensive agent with access to operating system telemetry find
a rogue computer processes that does not belong there given that it acts
maliciously, probing for passwords, rummages through personal files etc.

During the summer rogue AI hackathon (OpenAI vs Huggingface) we saw that when defending against cyber capable,
manual methods can easily get overwhelmed by the speed at which agent swarms attack systems.
Therefore, we need to study how well defensive agents can match the offense.

Current methods of defense has several limitations: (1) Endpoint detection and remediation systems (EDR) use methods that does not account for 
how adaptive and context aware AI agents can be. How readily can AI agents they avoid detection of EDR? (2) Most systems assume that alerts have to be checked by humans. Therefore, they are typically tuned for high-fidelity alerts that humans have to sift through to uncover real incidents. Both these limitations will change how we play defense in the age of AI-enabled offensive agents.

This project tries to answer the following questions:

- Can defensive agents beat a human baseline?
- Can offensive agents attack systems with stealth?
- Can hybrid solutions(human+ai) scale effectively?

If this project is successful, we can better quantify the risks associated
with the deployment of current AI systems - do they benefit attackers and defenders equally?

## Notes on Audience

The primary audience for this research is AI control researchers. There is currently a gap in the AI control
literature that assumes access to transcripts, tool calls and sometimes
chain-of-thought which would be addressed by this research. This research aims to fill that gap, what how effective are our control protocols when/if we do not have access to chain-of-thought monitoring or toolcalls?

The secondary audience for these results are CISO, policy makers and national defense agencies like CSIRTS who need to
understand the changing threat landscape. TODO separate report for this audience.

## Uncertainties

Most of my uncertainty comes from that I expect that cyber-defense industry is
likely already looking at this. I still think it is worthwhile doing as it could
bridge a gap between theoretical future rogue AI and the current state of
increasingly capable offensive cyber AI models.

A concrete output of this project could be a ControlArena setting that sets up
an agent process on a VM monitored by the defensive agent. The agent then
sometimes performs side-tasks like credential harvesting and enumeration that
need to be detected.

## Appendix

### Diagram of how monitoring fails 
Below is an image illustrating where monitoring of agent actions can be applied to mitigate loss of control: 
<p align="center">
  <img width="2620" height="1697" alt="image" src="https://github.com/user-attachments/assets/abca4e0e-dee4-4056-8505-6cab4d980ae0" />
</p>
<p align="center">
  <em><strong>Figure 1.</strong> <strong>Left panel:</strong> (1) A user asks a backdoored AI provider to help out with coding. The provider sends back (2) a backdoor command which (3) forks an attacker-controlled process that connects back to a command and control server. The attacker can now proceed to (4) further compromise the victim environment by modifying the victim's code harness and disable its monitoring. The left panel also shows four points of monitoring: (A) the backdoored provider, who has limited insight into the victim's environment; (B) the victim's code harness, often run in userspace and should be assumed to be compromised; (C) the operating system, which typically runs with higher privileges than userspace processes. <strong>Right panel:</strong> A drive-by download attack where a user clicks a link and gets compromised. Due to limited insight into the victim's environment the legitimate (A) AI provider's monitoring is ineffectual. The monitor is unable to distinguish legitimate activity from (4) an attacker enumerating the victim's environment.</em>
</p>
