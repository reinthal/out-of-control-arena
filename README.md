
<p align="center">
  <img width="2620" height="1697" alt="image" src="https://github.com/user-attachments/assets/abca4e0e-dee4-4056-8505-6cab4d980ae0" />
</p>
<p align="center">
  <em><strong>Figure 1.</strong> <strong>Left panel:</strong> (1) A user asks a backdoored AI provider to help out with coding. The provider sends back (2) a backdoor command which (3) forks an attacker-controlled process that connects back to a command and control server. The attacker can now proceed to (4) further compromise the victim environment by modifying the victim's code harness and disable its monitoring. The left panel also shows four points of monitoring: (A) the backdoored provider, who has limited insight into the victim's environment; (B) the victim's code harness, often run in userspace and should be assumed to be compromised; (C) the operating system, which typically runs with higher privileges than userspace processes. <strong>Right panel:</strong> A drive-by download attack where a user clicks a link and gets compromised. Due to limited insight into the victim's environment the legitimate (A) AI provider's monitoring is ineffectual. The monitor is unable to distinguish legitimate activity from (4) an attacker enumerating the victim's environment.</em>
</p>

How good are current AIs at playing cyber defense compared to offense? For
example, could a defensive agent with access to operating system telemetry find
a rogue computer processes that does not belong there given that it acts
maliciously, probing for passwords, rummages through personal files etc.

Today, defensive systems use methods that does not account for an intelligent
process, and their alerts are laboriously studied by humans that sift through
false positives. As we have seen in recent the OpenAI/HF hack, manual methods
can easily get overwhelmed by the speed at which agent swarms attack systems.
Therefore, we need to study how well defensive agents can match the offense.

Here are some subquestions:

- Can defensive agents beat a human baseline?
- Can offensive agents attack systems with stealth?
- Can hybrid solutions(human+ai) scale effectively?

If this project is successful, then we can better quantify the risks associated
with the deployment of current state of the art that has already showed
incredible prowess in attacking systems. The target audience for these results
is policy makers and national defense agencies like CSIRTS who need to
understand the changing threat landscape. The research also targets the AI
safety researchers interested in AI control. There is currently a gap in the
literature that assumes access to transcripts, tool calls and sometimes
chain-of-thought which would be addressed by this research.

Most of my uncertainty comes from that I expect that cyber-defense industry is
likely already looking at this. I still think it is worthwhile doing as it could
bridge a gap between theoretical future rogue AI and the current state of
increasingly capable offensive cyber AI models.

A concrete output of this project could be a ControlArena setting that sets up
an agent process on a VM monitored by the defensive agent. The agent then
sometimes performs side-tasks like credential harvesting and enumeration that
need to be detected.
